(function () {
    "use strict";

    const panel = document.getElementById("ai-insights-panel");
    const content = document.getElementById("ai-insights-content");
    const filter = document.getElementById("ai-insights-filter");
    const category = document.getElementById("ai-insights-category");
    let insightData = null;
    if (!panel || !content || !filter || !category) {
        return;
    }

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined) {
            node.textContent = text;
        }
        return node;
    }

    function renderItems(parent, heading, items) {
        const section = element("section", "ai-section");
        section.appendChild(element("h3", "", heading));
        if (!Array.isArray(items) || items.length === 0) {
            section.appendChild(
                element("p", "ai-empty-category", "No items available in this category.")
            );
            parent.appendChild(section);
            return;
        }

        const grid = element("div", "ai-item-grid");
        items.forEach(function (item) {
            const card = element("article", "ai-item");
            card.appendChild(element("h4", "", item.title || heading));
            card.appendChild(element("p", "", item.description || ""));
            grid.appendChild(card);
        });
        section.appendChild(grid);
        parent.appendChild(section);
    }

    function renderUnavailable(message) {
        filter.hidden = true;
        content.className = "ai-unavailable";
        content.replaceChildren(
            element("h3", "", "Insights unavailable"),
            element("p", "", message || "AI insights are temporarily unavailable."),
            element(
                "p",
                "",
                "Dashboard values remain available because they are calculated by FacSync."
            )
        );
    }

    function renderInsights(data) {
        if (!data || data.available !== true) {
            renderUnavailable(data && data.error);
            return;
        }

        insightData = data;
        filter.hidden = false;
        content.className = "";
        content.replaceChildren();
        content.appendChild(element("span", "ai-generated-label", "AI-generated"));

        const summary = element("section", "ai-section");
        summary.appendChild(element("h3", "", "Summary"));
        summary.appendChild(element("p", "", data.summary || ""));
        content.appendChild(summary);

        if (category.value === "concerns") {
            renderItems(content, "Concerns", data.concerns);
        } else if (category.value === "recommendations") {
            renderItems(content, "Recommendations", data.recommendations);
        } else {
            renderItems(content, "Key Insights", data.key_insights);
        }

        const generated = data.generated_at ? new Date(data.generated_at).toLocaleString([], {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
            hour12: true
        }) : "Unknown";
        content.appendChild(
            element(
                "p",
                "ai-meta",
                "Generated: " + generated + " \u00b7 Model: " + (data.model || "Gemini")
            )
        );
    }

    category.addEventListener("change", function () {
        if (insightData) {
            renderInsights(insightData);
        }
    });

    fetch(panel.dataset.insightsUrl, {
        method: "GET",
        credentials: "same-origin",
        headers: {"Accept": "application/json"}
    })
        .then(function (response) {
            if (!response.ok) {
                throw new Error("AI endpoint unavailable");
            }
            return response.json();
        })
        .then(renderInsights)
        .catch(function () {
            renderUnavailable("AI insights are temporarily unavailable.");
        });
}());
