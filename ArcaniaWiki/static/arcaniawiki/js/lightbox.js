/*
 * Image preview window.
 *
 * Links marked with data-lightbox open their image in a window in the middle
 * of the page instead of a new tab. Close it with the × button, the Esc key,
 * or by clicking outside the image. Without JavaScript the link still opens
 * the image itself.
 */
(function () {
    "use strict";

    let dialog = null;
    let image = null;

    function build() {
        dialog = document.createElement("dialog");
        dialog.className = "lightbox";
        dialog.setAttribute("aria-label", "Image preview");

        const close = document.createElement("button");
        close.type = "button";
        close.className = "lightbox__close";
        close.setAttribute("aria-label", "Close");
        close.textContent = "×";
        close.addEventListener("click", function () {
            dialog.close();
        });

        image = document.createElement("img");
        image.className = "lightbox__image";
        image.alt = "";

        dialog.append(close, image);

        // A click on the dark backdrop (outside the image) also closes it.
        dialog.addEventListener("click", function (event) {
            if (event.target === dialog) {
                dialog.close();
            }
        });
        dialog.addEventListener("close", function () {
            image.removeAttribute("src");
            document.documentElement.classList.remove("lightbox-open");
        });

        document.body.append(dialog);
    }

    function open(link) {
        if (!dialog) {
            build();
        }
        const thumb = link.querySelector("img");
        image.src = link.href;
        image.alt = thumb ? thumb.alt : "";
        document.documentElement.classList.add("lightbox-open");
        dialog.showModal(); // Esc closes a modal dialog natively.
    }

    document.addEventListener("click", function (event) {
        const link = event.target.closest("a[data-lightbox]");
        if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.button !== 0) {
            return; // let Ctrl/Cmd/Shift-click keep their usual browser behaviour
        }
        if (typeof HTMLDialogElement === "undefined") {
            return; // very old browser: follow the link
        }
        event.preventDefault();
        open(link);
    });
})();
