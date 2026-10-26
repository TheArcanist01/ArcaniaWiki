/*
 * Real-time list filtering.
 *
 * <input data-live-filter="#list-id"> narrows the elements with a
 * [data-filter-text] attribute inside #list-id as the user types.
 * An element with [data-filter-empty] inside the list is shown when
 * nothing matches. The current query is kept in the URL (?q=) and in
 * links marked [data-keep-filter] (column sorting), so it survives a
 * re-sort or a page reload.
 */
(function () {
    "use strict";

    function normalize(text) {
        return (text || "")
            .toLowerCase()
            .normalize("NFD")
            .replace(/[̀-ͯ]/g, "")
            .replace(/\s+/g, " ")
            .trim();
    }

    function withQuery(href, query) {
        const url = new URL(href, window.location.href);
        if (query) {
            url.searchParams.set("q", query);
        } else {
            url.searchParams.delete("q");
        }
        return url.pathname + url.search + url.hash;
    }

    function setUpFilter(input) {
        const list = document.querySelector(input.dataset.liveFilter);
        if (!list) {
            return;
        }

        const rows = Array.from(list.querySelectorAll("[data-filter-text]"));
        const rowTexts = rows.map((row) => normalize(row.dataset.filterText));
        const emptyState = list.querySelector("[data-filter-empty]");
        const counter = input.parentElement.querySelector("[data-live-filter-count]");
        const keepLinks = document.querySelectorAll("[data-keep-filter]");
        const noun = input.dataset.noun || "entry";
        const nounPlural = input.dataset.nounPlural || noun + "s";

        const initialQuery = new URLSearchParams(window.location.search).get("q");
        if (initialQuery) {
            input.value = initialQuery;
        }

        function label(count) {
            return count === 1 ? noun : nounPlural;
        }

        function apply() {
            const query = input.value.trim();
            const terms = normalize(query).split(" ").filter(Boolean);
            let visible = 0;

            rows.forEach((row, index) => {
                const matches = terms.every((term) => rowTexts[index].includes(term));
                row.hidden = !matches;
                if (matches) {
                    visible += 1;
                }
            });

            if (emptyState) {
                emptyState.hidden = rows.length === 0 || visible > 0;
            }
            if (counter) {
                counter.textContent = terms.length
                    ? `${visible} of ${rows.length} ${label(rows.length)}`
                    : `${rows.length} ${label(rows.length)}`;
            }

            window.history.replaceState(null, "", withQuery(window.location.href, query));
            keepLinks.forEach((link) => {
                link.setAttribute("href", withQuery(link.getAttribute("href"), query));
            });
        }

        input.addEventListener("input", apply);
        input.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
            }
        });
        apply();
    }

    document.querySelectorAll("[data-live-filter]").forEach(setUpFilter);
})();
