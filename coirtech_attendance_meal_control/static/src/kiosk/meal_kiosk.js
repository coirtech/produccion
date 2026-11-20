/** @odoo-module **/

import { onWillStart, onWillUnmount, useState } from "@odoo/owl";
import KioskApp from "@hr_attendance/public_kiosk/public_kiosk_app";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

const CUSTOM_DISPLAYS = new Set(["coir_meal", "coir_meal_result", "coir_meal_error"]);
const IDENTITY_TIMEOUT = 110000;

// The standard public kiosk remains in use. Identification opens an action
// selector; neither selecting a name nor scanning a badge toggles attendance.
patch(KioskApp.kioskAttendanceApp.prototype, {
    setup() {
        super.setup(...arguments);
        this.coirMeal = useState({
            ready: false,
            enabled: false,
            busy: false,
            configFailed: false,
            ticket: null,
            employee: null,
            snapshot: null,
            confirmCheckout: false,
            error: "",
            message: "",
            timeLabel: "",
        });
        this.coirMealActions = [
            { key: "check_in", label: _t("Entrada"), detail: _t("Iniciar la jornada"), icon: "fa-sign-in" },
            { key: "meal_start", label: _t("Salir a comer"), detail: _t("Registrar la salida a comida"), icon: "fa-cutlery" },
            { key: "meal_return", label: _t("Regresar de comida"), detail: _t("Registrar el regreso al trabajo"), icon: "fa-rotate-left" },
            { key: "work_exit", label: _t("Salida de trabajo"), detail: _t("Salida temporal pagada"), icon: "fa-external-link" },
            { key: "work_return", label: _t("Regreso al trabajo"), detail: _t("Volver de la salida temporal"), icon: "fa-reply" },
            { key: "check_out", label: _t("Salida final"), detail: _t("Terminar la jornada"), icon: "fa-sign-out" },
        ];
        this.coirMealIdentityTimer = null;
        this.coirMealResultTimer = null;
        this.coirMealDelay = 5000;
        this.coirMealMounted = true;
        this.coirMealSerial = 0;
        onWillStart(() => this.coirLoadConfig());
        onWillUnmount(() => {
            this.coirMealMounted = false;
            this.coirMealSerial++;
            this.coirClearTimers();
            this.coirForgetIdentity();
        });
    },

    async coirLoadConfig() {
        this.coirMeal.busy = true;
        try {
            const config = await rpc("/coirtech_meal/config", { token: this.props.token });
            if (!config || typeof config.enabled !== "boolean") {
                throw new Error(_t("No se recibió una configuración válida del quiosco."));
            }
            if (!this.coirMealMounted) {
                return;
            }
            this.coirMeal.enabled = config.enabled;
            this.coirMeal.ready = true;
            this.coirMeal.configFailed = false;
            this.coirMeal.error = "";
            if (Number.isFinite(config.kiosk_delay)) {
                this.coirMealDelay = Math.min(30000, Math.max(1500, config.kiosk_delay));
            }
            if (this.state.active_display === "coir_meal_error") {
                this.coirMeal.busy = false;
                this.kioskReturn();
            }
        } catch (error) {
            if (!this.coirMealMounted) {
                return;
            }
            // Fail closed: a missing configuration request must never fall back
            // to the native check-in/out toggle while the extension may be on.
            this.coirMeal.ready = false;
            this.coirMeal.configFailed = true;
            this.coirMeal.error = _t("No se pudo cargar el control de comidas. Comprueba la conexión y vuelve a intentar.");
            this.state.active_display = "coir_meal_error";
        } finally {
            if (this.coirMealMounted) {
                this.coirMeal.busy = false;
            }
        }
    },

    switchDisplay(screen) {
        if (this.coirMeal && CUSTOM_DISPLAYS.has(screen)) {
            this.state.active_display = screen;
            return;
        }
        return super.switchDisplay(...arguments);
    },

    coirClearTimers() {
        clearTimeout(this.coirMealIdentityTimer);
        clearTimeout(this.coirMealResultTimer);
        this.coirMealIdentityTimer = null;
        this.coirMealResultTimer = null;
    },

    coirForgetIdentity() {
        if (!this.coirMeal) {
            return;
        }
        this.coirMeal.ticket = null;
        this.coirMeal.employee = null;
        this.coirMeal.snapshot = null;
        this.coirMeal.confirmCheckout = false;
        this.employeeData = null;
    },

    kioskReturn() {
        if (this.coirMeal && this.coirMeal.busy) {
            return;
        }
        if (this.coirMeal) {
            this.coirMealSerial++;
            this.coirClearTimers();
            this.coirForgetIdentity();
            this.coirMeal.error = "";
            this.coirMeal.message = "";
            this.coirMeal.timeLabel = "";
            if (this.coirMeal.configFailed) {
                this.state.active_display = "coir_meal_error";
                return;
            }
        }
        return super.kioskReturn(...arguments);
    },

    async kioskConfirm(employeeId) {
        if (!this.coirMeal.ready || this.coirMeal.busy) {
            return;
        }
        if (!this.coirMeal.enabled) {
            return super.kioskConfirm(...arguments);
        }
        this.coirMeal.busy = true;
        const serial = this.coirMealSerial;
        try {
            // Reuse the existing read-only employee identification step and
            // native PIN component, without invoking manual_selection.
            const employee = await rpc("/hr_attendance/attendance_employee_data", {
                token: this.props.token,
                employee_id: employeeId,
            });
            if (!this.coirMealMounted || serial !== this.coirMealSerial) {
                return;
            }
            if (!employee || !employee.employee_name) {
                this.displayNotification(_t("No se encontró al empleado en esta empresa."));
                return;
            }
            if (Number.isFinite(employee.kiosk_delay)) {
                this.coirMealDelay = Math.min(30000, Math.max(1500, employee.kiosk_delay));
            }
            if (employee.use_pin) {
                this.employeeData = { ...employee, coir_meal_identity: true };
                this.switchDisplay("pin");
            } else {
                await this.coirIdentify({ employee_id: employeeId, pin_code: false });
            }
        } catch (error) {
            this.coirShowIdentificationError(error);
        } finally {
            if (this.coirMealMounted) {
                this.coirMeal.busy = false;
            }
        }
    },

    async onManualSelection(employeeId, enteredPin) {
        if (!this.coirMeal.ready || this.coirMeal.busy) {
            return;
        }
        if (!this.coirMeal.enabled) {
            return super.onManualSelection(...arguments);
        }
        this.coirMeal.busy = true;
        try {
            // enteredPin is used only for this request; it is never stored in
            // component state, browser storage, or an action request.
            await this.coirIdentify({ employee_id: employeeId, pin_code: enteredPin });
        } catch (error) {
            this.coirShowIdentificationError(error);
        } finally {
            if (this.coirMealMounted) {
                this.coirMeal.busy = false;
            }
        }
    },

    async onBarcodeScanned(barcode) {
        if (!this.coirMeal.ready || this.coirMeal.busy) {
            return;
        }
        if (!this.coirMeal.enabled) {
            return super.onBarcodeScanned(...arguments);
        }
        if (this.lockScanner || this.state.active_display !== "main") {
            return;
        }
        this.lockScanner = true;
        this.coirMeal.busy = true;
        try {
            await this.coirIdentify({ barcode });
        } catch (error) {
            this.coirShowIdentificationError(error);
        } finally {
            this.lockScanner = false;
            if (this.coirMealMounted) {
                this.coirMeal.busy = false;
            }
        }
    },

    async coirIdentify(credentials) {
        const serial = this.coirMealSerial;
        const result = await rpc("/coirtech_meal/identify", {
            token: this.props.token,
            ...credentials,
        });
        if (!this.coirMealMounted || serial !== this.coirMealSerial) {
            return;
        }
        if (!result || !result.ok || !result.ticket || !result.employee || !result.snapshot) {
            this.displayNotification(result?.error || _t("No se pudo verificar la identificación. Revisa el PIN o la credencial."));
            return;
        }
        this.coirClearTimers();
        if (Number.isFinite(result.kiosk_delay)) {
            this.coirMealDelay = Math.min(30000, Math.max(1500, result.kiosk_delay));
        }
        this.coirMeal.ticket = result.ticket;
        this.coirMeal.employee = { id: result.employee.id, name: result.employee.name };
        this.coirMeal.snapshot = result.snapshot;
        this.coirMeal.confirmCheckout = false;
        this.coirMeal.error = "";
        this.coirMeal.message = "";
        this.employeeData = null;
        this.switchDisplay("coir_meal");
        // This is an identity-session expiry, not a food-duration alert.
        // It never writes attendance, closes a meal, or posts a notification.
        this.coirMealIdentityTimer = setTimeout(() => this.kioskReturn(), IDENTITY_TIMEOUT);
    },

    coirShowIdentificationError(error) {
        if (this.coirMealMounted) {
            this.displayNotification(error?.data?.message || _t("No se pudo verificar la identificación. Comprueba la conexión e intenta nuevamente."));
        }
    },

    coirCanAction(action) {
        return Boolean(
            this.coirMeal.ticket &&
            this.coirMeal.snapshot?.allowed_actions?.includes(action)
        );
    },

    coirStateLabel() {
        return {
            absent: _t("Sin jornada abierta"),
            working: _t("En jornada"),
            eating: _t("En comida"),
            away: _t("Fuera por trabajo"),
            returned: _t("En jornada, comida registrada"),
            closed: _t("Jornada finalizada"),
        }[this.coirMeal.snapshot?.state] || _t("Selecciona un movimiento");
    },

    async coirChooseAction(action) {
        if (this.coirMeal.busy || !this.coirCanAction(action)) {
            return;
        }
        await this.coirSubmitAction(action, false);
    },

    async coirSubmitAction(action, confirmWithoutReturn = false) {
        if (this.coirMeal.busy || !this.coirCanAction(action)) {
            return;
        }
        this.coirMeal.busy = true;
        this.coirClearTimers();
        try {
            const result = await this.makeRpcWithGeolocation("/coirtech_meal/action", {
                token: this.props.token,
                ticket: this.coirMeal.ticket,
                action,
                confirm_without_return: confirmWithoutReturn,
            });
            if (!this.coirMealMounted) {
                return;
            }
            if (!result || !result.ok) {
                this.coirActionFailed(result?.error || _t("No se pudo confirmar el movimiento. Identifícate nuevamente para revisar el estado actual."));
                return;
            }
            this.coirMeal.ticket = null;
            this.coirMeal.snapshot = result.snapshot || null;
            this.coirMeal.confirmCheckout = false;
            this.coirMeal.message = result.message || _t("Movimiento registrado.");
            this.coirMeal.timeLabel = result.time_label || "";
            this.employeeData = null;
            this.switchDisplay("coir_meal_result");
            this.coirMealResultTimer = setTimeout(() => this.kioskReturn(), this.coirMealDelay);
        } catch (error) {
            if (this.coirMealMounted) {
                this.coirActionFailed(_t("No se pudo confirmar la respuesta del servidor. Identifícate de nuevo para revisar el último movimiento antes de repetirlo."));
            }
        } finally {
            if (this.coirMealMounted) {
                this.coirMeal.busy = false;
            }
        }
    },

    coirActionFailed(message) {
        this.coirMeal.ticket = null;
        this.coirMeal.snapshot = null;
        this.coirMeal.confirmCheckout = false;
        this.coirMeal.configFailed = false;
        this.coirMeal.error = message;
        this.employeeData = null;
        this.switchDisplay("coir_meal_error");
    },
});
