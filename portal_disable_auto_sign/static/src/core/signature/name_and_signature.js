/** @odoo-module **/

import { onMounted } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { NameAndSignature } from "@web/core/signature/name_and_signature";

patch(NameAndSignature.prototype, {
    setup() {
        super.setup(...arguments);

        if (this.state && this.state.signMode === "auto") {
            this.state.signMode = "draw";
        }

        onMounted(() => {
            try {
                // Cambiar a modo 'draw' una vez que el canvas ya existe en el DOM
                if (this.state && this.state.signMode === "auto") {
                    if (typeof this.setMode === "function") {
                        this.setMode("draw");
                    } else if (typeof this.onClickSignDraw === "function") {
                        this.onClickSignDraw();
                    } else {
                        this.state.signMode = "draw";
                    }
                }

                // Ocultar el botón de firma automática en el DOM de forma segura
                const rootEl = this.__owl__?.bdom?.el || document;
                const autoButtons = rootEl.querySelectorAll(
                    ".o_web_sign_auto_button, [data-mode='auto']"
                );
                autoButtons.forEach((el) => el.classList.add("d-none"));

                // Respaldo por si Odoo 19 usa botones de pestaña sin la clase clásica
                const tabButtons = rootEl.querySelectorAll(
                    ".o_web_sign_name_and_signature button, .o_web_sign_name_and_signature .nav-link"
                );
                tabButtons.forEach((btn) => {
                    const label = (btn.textContent || "").trim().toLowerCase();
                    if (label === "auto" || label === "automática" || label === "automatica") {
                        btn.classList.add("d-none");
                    }
                });
            } catch (err) {
                console.warn("[portal_disable_auto_sign] Aviso al inicializar firma:", err);
            }
        });
    },

    onClickSignAuto() {
        if (typeof this.onClickSignDraw === "function") {
            return this.onClickSignDraw(...arguments);
        }
        if (typeof this.setMode === "function") {
            return this.setMode("draw");
        }
        if (this.state) {
            this.state.signMode = "draw";
        }
    },

    setMode(mode, ...rest) {
        const safeMode = mode === "auto" ? "draw" : mode;
        if (super.setMode) {
            return super.setMode(safeMode, ...rest);
        }
    },
});
