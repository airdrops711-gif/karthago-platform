/* Karthago Commerce frontend JavaScript */
(function () {
    "use strict";

    function openCheckout() {
        var modal = document.getElementById("checkout-modal");
        if (!modal) return;
        modal.classList.remove("hidden");
        document.body.classList.add("overflow-hidden");
        // Focus the first field so the modal is usable with the keyboard.
        var first = modal.querySelector("input[name='full_name']");
        if (first) setTimeout(function () { first.focus(); }, 50);
    }

    function closeCheckout() {
        var modal = document.getElementById("checkout-modal");
        if (!modal) return;
        modal.classList.add("hidden");
        document.body.classList.remove("overflow-hidden");
    }

    // Expose the modal control for the inline onclick handlers.
    window.karthago = window.karthago || {};
    window.karthago.openCheckout = openCheckout;
    window.karthago.closeCheckout = closeCheckout;

    document.addEventListener("DOMContentLoaded", function () {
        // Any element with [data-open-checkout] opens the modal.
        document.querySelectorAll("[data-open-checkout]").forEach(function (el) {
            el.addEventListener("click", function (e) {
                e.preventDefault();
                openCheckout();
            });
        });

        // Close on the overlay and on Escape.
        document.querySelectorAll("[data-close-checkout]").forEach(function (el) {
            el.addEventListener("click", function (e) {
                e.preventDefault();
                closeCheckout();
            });
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") closeCheckout();
        });

        // Tunisian phone: exactly 8 digits.
        document.querySelectorAll("input[name='phone']").forEach(function (input) {
            input.addEventListener("input", function () {
                this.value = this.value.replace(/[^0-9]/g, "").slice(0, 8);
            });
        });

        // The cart badge is rendered in two places (desktop + mobile
        // navbar). Every HTMX badge update must refresh both.
        document.body.addEventListener("htmx:afterSwap", function (event) {
            var target = event.detail && event.detail.target;
            if (target && target.id === "cart-badge") {
                document.querySelectorAll("[data-cart-badge]").forEach(function (el) {
                    el.textContent = target.textContent;
                });
            }
        });
    });
})();
