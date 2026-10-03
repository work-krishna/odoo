import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("ci_account_report_tour", {
    steps: () => [
        {
            content: "The balance sheet is rendered",
            trigger: ".o_ci_account_report .o_ci_report_table tr.o_ci_section:contains('ASSETS')",
        },
        {
            content: "Open the options",
            trigger: ".o_ci_filters button:contains('Options')",
            run: "click",
        },
        {
            content: "Unfold all lines",
            trigger: ".dropdown-item:contains('Unfold All')",
            run: "click",
        },
        {
            content: "Account lines are shown",
            trigger: ".o_ci_report_table tr:not(.o_ci_group):not(.o_ci_section):not(.o_ci_total) .o_ci_name",
        },
        {
            content: "Change the date",
            trigger: ".o_ci_filters button:contains('As of')",
            run: "click",
        },
        {
            content: "End of last fiscal year",
            trigger: ".dropdown-item:contains('End of Last Fiscal Year')",
            run: "click",
        },
        {
            content: "The report reloaded",
            trigger: ".o_ci_account_report:not(.o_ci_loading) .o_ci_report_table tr.o_ci_total",
        },
    ],
});
