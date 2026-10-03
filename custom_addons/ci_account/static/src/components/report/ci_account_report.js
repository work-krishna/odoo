import { Component, onWillStart, useState } from "@odoo/owl";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, serializeDate } from "@web/core/l10n/dates";
import { download } from "@web/core/network/download";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const NUMERIC_FIGURES = ["monetary", "percentage", "float"];

/**
 * Client action rendering a ci.account.report.* model: filters in the control
 * panel, foldable lines (lazy ones are fetched on unfold), drill-down to
 * journal items / general ledger / documents, PDF and XLSX exports.
 */
export class CiAccountReport extends Component {
    static template = "ci_account.Report";
    static components = { ControlPanel, DateTimeInput, Dropdown, DropdownItem, MultiRecordSelector };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.ui = useService("ui");
        const context = this.props.action.context || {};
        this.reportModel = context.report_model;
        this.state = useState({
            data: null,
            loading: false,
            customFrom: null,
            customTo: null,
            numberPeriod: 1,
        });
        useSetupAction({
            getLocalState: () => ({ options: this.state.data?.options }),
        });
        const initialOptions = this.props.state?.options || context.ci_report_options || {};
        if (context.report_id && !initialOptions.report_id) {
            initialOptions.report_id = context.report_id;
        }
        onWillStart(() => this.load(initialOptions));
    }

    // -------------------------------------------------------------------------
    // Data
    // -------------------------------------------------------------------------

    get data() {
        return this.state.data;
    }

    get options() {
        return this.state.data.options;
    }

    hasFilter(name) {
        return this.data.filters.includes(name);
    }

    async load(options) {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(this.reportModel, "get_report_information", [options]);
            const { date, comparison } = this.state.data.options;
            this.state.customFrom = deserializeDate(date.date_from);
            this.state.customTo = deserializeDate(date.date_to);
            this.state.numberPeriod = comparison.number_period || 1;
        } finally {
            this.state.loading = false;
        }
    }

    reload(changes = {}) {
        return this.load({ ...this.options, ...changes });
    }

    get visibleLines() {
        const byId = new Map(this.data.lines.map((line) => [line.id, line]));
        return this.data.lines.filter((line) => {
            let parent = byId.get(line.parent_id);
            while (parent) {
                if (parent.unfoldable && !parent.unfolded) {
                    return false;
                }
                parent = byId.get(parent.parent_id);
            }
            return true;
        });
    }

    _descendantsEnd(index) {
        // index after the last descendant of the line at ``index``
        const lines = this.data.lines;
        const ancestorIds = new Set([lines[index].id]);
        let end = index + 1;
        while (end < lines.length && ancestorIds.has(lines[end].parent_id)) {
            ancestorIds.add(lines[end].id);
            end++;
        }
        return end;
    }

    async toggleLine(line) {
        if (!line.unfoldable) {
            return;
        }
        const options = this.options;
        if (line.unfolded) {
            line.unfolded = false;
            options.unfolded_lines = options.unfolded_lines.filter((id) => id !== line.id);
            return;
        }
        line.unfolded = true;
        if (!options.unfolded_lines.includes(line.id)) {
            options.unfolded_lines.push(line.id);
        }
        const index = this.data.lines.indexOf(line);
        const hasChildren = this.data.lines[index + 1]?.parent_id === line.id;
        if (line.lazy && !hasChildren) {
            const children = await this.orm.call(this.reportModel, "get_expanded_lines", [options, line.id]);
            this.data.lines.splice(this._descendantsEnd(this.data.lines.indexOf(line)), 0, ...children);
        }
    }

    async loadMore(line) {
        const children = await this.orm.call(this.reportModel, "get_expanded_lines", [
            this.options,
            line.parent_id,
            line.load_more,
        ]);
        const index = this.data.lines.indexOf(line);
        this.data.lines.splice(index, 1, ...children);
    }

    async openLine(line, target) {
        const action = await this.orm.call(this.reportModel, "action_open_line", [
            this.options,
            line.id,
            target,
        ]);
        if (action) {
            await this.actionService.doAction(action);
        }
    }

    onNameClick(line) {
        if (line.load_more) {
            return this.loadMore(line);
        }
        if (line.unfoldable) {
            return this.toggleLine(line);
        }
        if (line.actions.length) {
            return this.openLine(line, line.actions[0].target);
        }
    }

    onCellClick(line, cell) {
        if (cell.no_format === null || !line.actions.length) {
            return;
        }
        const action = line.actions.find((a) => a.target === "journal_items") || line.actions[0];
        return this.openLine(line, action.target);
    }

    // -------------------------------------------------------------------------
    // Rendering helpers
    // -------------------------------------------------------------------------

    isNumeric(figure) {
        return NUMERIC_FIGURES.includes(figure);
    }

    lineClass(line) {
        const classes = [line.class || ""];
        if (line.unfoldable) {
            classes.push("o_ci_foldable");
        }
        if (line.load_more) {
            classes.push("o_ci_load_more");
        }
        return classes.join(" ");
    }

    cellClass(line, cell) {
        const classes = [];
        if (this.isNumeric(cell.figure)) {
            classes.push("text-end", "text-nowrap");
            if (cell.no_format < 0) {
                classes.push("o_ci_negative");
            }
            if (cell.no_format !== null && line.actions.length) {
                classes.push("o_ci_clickable");
            }
        } else {
            classes.push("o_ci_text_cell");
        }
        return classes.join(" ");
    }

    indentStyle(line) {
        return `padding-left: ${0.5 + 1.25 * (line.level || 0)}rem;`;
    }

    // -------------------------------------------------------------------------
    // Filters
    // -------------------------------------------------------------------------

    get dateFilters() {
        if (this.data.date_mode === "single") {
            return [
                ["today", _t("Today")],
                ["this_month", _t("End of This Month")],
                ["this_quarter", _t("End of This Quarter")],
                ["this_year", _t("End of This Fiscal Year")],
                ["last_month", _t("End of Last Month")],
                ["last_quarter", _t("End of Last Quarter")],
                ["last_year", _t("End of Last Fiscal Year")],
            ];
        }
        return [
            ["this_month", _t("This Month")],
            ["this_quarter", _t("This Quarter")],
            ["this_year", _t("This Fiscal Year")],
            ["last_month", _t("Last Month")],
            ["last_quarter", _t("Last Quarter")],
            ["last_year", _t("Last Fiscal Year")],
        ];
    }

    setDateFilter(filter) {
        return this.reload({ date: { filter } });
    }

    applyCustomDate() {
        const date = {
            filter: "custom",
            date_from: serializeDate(this.state.customFrom || this.state.customTo),
            date_to: serializeDate(this.state.customTo || this.state.customFrom),
        };
        return this.reload({ date });
    }

    get comparisonFilters() {
        return [
            ["no_comparison", _t("No Comparison")],
            ["previous_period", _t("Previous Period")],
            ["same_last_year", _t("Same Period Last Year")],
        ];
    }

    get comparisonLabel() {
        const comparison = this.options.comparison;
        if (comparison.filter === "no_comparison") {
            return _t("Comparison");
        }
        const label = this.comparisonFilters.find(([key]) => key === comparison.filter)[1];
        return comparison.number_period > 1 ? `${label} (${comparison.number_period})` : label;
    }

    setComparison(filter) {
        const number_period = Math.max(1, Math.min(12, parseInt(this.state.numberPeriod) || 1));
        return this.reload({ comparison: { filter, number_period } });
    }

    get journalsLabel() {
        const selected = this.options.journals.filter((j) => j.selected);
        if (!selected.length || selected.length === this.options.journals.length) {
            return _t("All Journals");
        }
        return selected.map((j) => j.code).join(", ");
    }

    toggleJournal(journal) {
        journal.selected = !journal.selected;
        return this.reload();
    }

    clearJournals() {
        for (const journal of this.options.journals) {
            journal.selected = false;
        }
        return this.reload();
    }

    get optionToggles() {
        const toggles = [];
        if (this.hasFilter("draft")) {
            toggles.push(["all_entries", _t("Include Draft Entries")]);
        }
        if (this.hasFilter("unfold_all")) {
            toggles.push(["unfold_all", _t("Unfold All")]);
        }
        if (this.hasFilter("hide_zero")) {
            toggles.push(["hide_zero", _t("Hide Lines at 0")]);
        }
        if (this.hasFilter("hierarchy")) {
            toggles.push(["hierarchy", _t("Hierarchy and Subtotals")]);
        }
        if (this.hasFilter("unreconciled")) {
            toggles.push(["unreconciled", _t("Unreconciled Entries Only")]);
        }
        return toggles;
    }

    toggleOption(key) {
        const changes = { [key]: !this.options[key] };
        if (key === "unfold_all" && this.options.unfold_all) {
            changes.unfolded_lines = [];
        }
        return this.reload(changes);
    }

    get accountTypes() {
        return [
            ["both", _t("Receivable and Payable")],
            ["receivable", _t("Receivable")],
            ["payable", _t("Payable")],
        ];
    }

    get accountTypeLabel() {
        return this.accountTypes.find(([key]) => key === this.options.account_type)[1];
    }

    get agingLabel() {
        return this.options.aging_based_on === "invoice_date" ? _t("Based on Invoice Date") : _t("Based on Due Date");
    }

    updatePartners(partnerIds) {
        return this.reload({ partner_ids: partnerIds });
    }

    updateAnalytic(analyticIds) {
        return this.reload({ analytic_account_ids: analyticIds });
    }

    clearAccounts() {
        return this.reload({ account_ids: [] });
    }

    // -------------------------------------------------------------------------
    // Buttons
    // -------------------------------------------------------------------------

    async export(fileType) {
        this.ui.block();
        try {
            await download({
                url: "/ci_account/report/export",
                data: {
                    report_model: this.reportModel,
                    options: JSON.stringify(this.options),
                    file_type: fileType,
                    context: JSON.stringify(user.context),
                },
            });
        } finally {
            this.ui.unblock();
        }
    }

    async callButton(button) {
        const action = await this.orm.call(this.reportModel, button.method, [this.options]);
        if (action) {
            await this.actionService.doAction(action, { onClose: () => this.reload() });
        }
    }
}

registry.category("actions").add("ci_account_report", CiAccountReport);
