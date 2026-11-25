/** @odoo-module **/

// Keep the existing public kiosk and its COIRTECH action selector.  This file
// adapts their identification endpoints to a configured group of companies;
// it deliberately does not implement a second scanner or a second interface.
import "@coirtech_attendance_meal_control/kiosk/meal_kiosk";
import { onWillUnmount } from "@odoo/owl";
import KioskApp from "@hr_attendance/public_kiosk/public_kiosk_app";
import { KioskManualSelection } from "@hr_attendance/components/manual_selection/manual_selection";
import { KioskBarcodeScanner } from "@hr_attendance/components/kiosk_barcode/kiosk_barcode";
import { Domain } from "@web/core/domain";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

const IDENTITY_TIMEOUT = 110000;
const isMultiCompanyKiosk = () => document.body.classList.contains("o_multi_company_kiosk");

patch(KioskManualSelection.prototype, {
    setup() {
        super.setup(...arguments);
        this.amckFetchSerial = 0;
        this.amckMounted = true;
        this.amckNotification = useService("notification");
        onWillUnmount(() => {
            this.amckMounted = false;
            this.amckFetchSerial++;
        });
    },

    async _fetchEmployeeData() {
        if (!isMultiCompanyKiosk()) {
            return super._fetchEmployeeData(...arguments);
        }
        const serial = ++this.amckFetchSerial;
        const domain = Domain.and([this.state.departmentDomain, this.state.searchDomain]).toList();
        // Native screen-size calculation can yield zero on a short viewport.
        this.state.limit = Math.min(200, Math.max(1, Math.trunc(this.state.limit) || 1));
        try {
            const results = await rpc("/attendance_multi_company/employees_infos", {
                token: this.props.token,
                limit: this.state.limit,
                offset: this.state.offset,
                domain,
            });
            if (!this.amckMounted || serial !== this.amckFetchSerial) {
                return;
            }
            if (!results?.ok || !Array.isArray(results.records) || !Number.isFinite(results.length)) {
                throw new Error(results?.error || _t("No se pudo cargar la lista de empleados."));
            }
            this.state.employeesData.records = results.records;
            this.state.employeesData.count = results.length;
        } catch (error) {
            if (!this.amckMounted || serial !== this.amckFetchSerial) {
                return;
            }
            this.state.employeesData.records = [];
            this.state.employeesData.count = 0;
            this.amckNotification.add(
                error?.data?.message || error.message || _t("No se pudo cargar la lista de empleados."),
                { type: "danger" }
            );
        }
    },
});

patch(KioskBarcodeScanner.prototype, {
    get installURL() {
        if (!isMultiCompanyKiosk()) {
            return super.installURL;
        }
        const path = `attendance_multi_company/${this.props.token}`;
        return `/scoped_app?app_id=hr_attendance&path=${encodeURIComponent(path)}`;
    },
});

patch(KioskApp.kioskAttendanceApp.prototype, {
    async kioskReturn() {
        if (!isMultiCompanyKiosk() || !this.coirMeal?.ticket) {
            return super.kioskReturn(...arguments);
        }
        if (this.coirMeal.busy) {
            return;
        }
        const ticket = this.coirMeal.ticket;
        this.coirMeal.busy = true;
        this.coirClearTimers();
        try {
            // Wait before allowing another identification. The ticket also
            // prevents a delayed cancellation from clearing a newer session.
            await rpc("/attendance_multi_company/cancel", { token: this.props.token, ticket });
        } catch {
            // Always discard local identity when returning. A disconnected
            // request must not keep another employee's action screen open.
        } finally {
            if (this.coirMealMounted) {
                this.coirMeal.busy = false;
                super.kioskReturn(...arguments);
            }
        }
    },

    async coirLoadConfig() {
        if (!isMultiCompanyKiosk()) {
            return super.coirLoadConfig(...arguments);
        }
        this.coirMeal.busy = true;
        try {
            const result = await rpc("/attendance_multi_company/config", { token: this.props.token });
            // A unified token must never reach Odoo's company-specific toggle
            // routes, including when the link has expired or was deactivated.
            if (!result?.ok || result.enabled !== true) {
                throw new Error(_t("No se recibió una configuración válida del quiosco."));
            }
            if (!this.coirMealMounted) {
                return;
            }
            this.coirMeal.enabled = true;
            this.coirMeal.ready = true;
            this.coirMeal.configFailed = false;
            this.coirMeal.error = "";
            if (this.state.active_display === "coir_meal_error") {
                this.coirMeal.busy = false;
                this.kioskReturn();
            }
        } catch (error) {
            if (!this.coirMealMounted) {
                return;
            }
            this.coirMeal.ready = false;
            this.coirMeal.configFailed = true;
            this.coirMeal.error = _t("No se pudo cargar el control de asistencia. Comprueba la conexión y vuelve a intentar.");
            this.state.active_display = "coir_meal_error";
        } finally {
            if (this.coirMealMounted) {
                this.coirMeal.busy = false;
            }
        }
    },

    async kioskConfirm(employeeId) {
        if (!isMultiCompanyKiosk()) {
            return super.kioskConfirm(...arguments);
        }
        if (!this.coirMeal.ready || this.coirMeal.busy) {
            return;
        }
        this.coirMeal.busy = true;
        const serial = this.coirMealSerial;
        try {
            const employee = await rpc("/attendance_multi_company/employee_data", {
                token: this.props.token,
                employee_id: employeeId,
            });
            if (!this.coirMealMounted || serial !== this.coirMealSerial) {
                return;
            }
            if (!employee?.employee_name) {
                this.displayNotification(_t("No se encontró al empleado entre las empresas de este quiosco."));
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

    async coirIdentify(credentials) {
        if (!isMultiCompanyKiosk()) {
            return super.coirIdentify(...arguments);
        }
        const serial = this.coirMealSerial;
        const result = await rpc("/attendance_multi_company/identify", {
            token: this.props.token,
            ...credentials,
        });
        if (!this.coirMealMounted || serial !== this.coirMealSerial) {
            return;
        }
        if (!result?.ok || !result.ticket || !result.employee || !result.snapshot) {
            this.displayNotification(result?.error || _t("No se pudo verificar la identificación. Revisa el PIN o la credencial."));
            return;
        }
        this.coirClearTimers();
        if (Number.isFinite(result.kiosk_delay)) {
            this.coirMealDelay = Math.min(30000, Math.max(1500, result.kiosk_delay));
        }
        this.coirMeal.ticket = result.ticket;
        this.coirMeal.employee = {
            id: result.employee.id,
            name: result.employee.name,
            company_name: result.employee.company_name,
        };
        this.amckDeviceTrackingEnabled = Boolean(
            result.device_tracking_enabled ?? result.employee.device_tracking_enabled
        );
        this.coirMeal.snapshot = result.snapshot;
        this.coirMeal.confirmCheckout = false;
        this.coirMeal.error = "";
        this.coirMeal.message = "";
        this.employeeData = null;
        this.switchDisplay("coir_meal");
        // Same silent identity expiry as the original module; never a meal
        // alert and never an attendance mutation.
        this.coirMealIdentityTimer = setTimeout(() => this.kioskReturn(), IDENTITY_TIMEOUT);
    },

    async makeRpcWithGeolocation(route, params) {
        if (!isMultiCompanyKiosk() || route !== "/coirtech_meal/action") {
            return super.makeRpcWithGeolocation(...arguments);
        }
        const unifiedRoute = "/attendance_multi_company/action";
        // Apply the identified employee's company setting, rather than the
        // setting of the first company used to bootstrap the native kiosk.
        if (!this.amckDeviceTrackingEnabled || !navigator.geolocation) {
            return rpc(unifiedRoute, { ...params });
        }
        this.ui.block();
        try {
            const coords = await new Promise((resolve) => {
                navigator.geolocation.getCurrentPosition(
                    ({ coords: { latitude, longitude } }) => resolve({ latitude, longitude }),
                    () => resolve({}),
                    { enableHighAccuracy: true }
                );
            });
            return await rpc(unifiedRoute, { ...params, ...coords });
        } finally {
            this.ui.unblock();
        }
    },
});
