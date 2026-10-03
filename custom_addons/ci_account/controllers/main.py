# -*- coding: utf-8 -*-
import json

from werkzeug.exceptions import BadRequest

from odoo import http
from odoo.http import content_disposition, request

EXPORT_TYPES = {
    'pdf': ('export_to_pdf', 'application/pdf'),
    'xlsx': ('export_to_xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
}


class CiAccountReportController(http.Controller):

    @http.route('/ci_account/report/export', type='http', auth='user', methods=['POST'], readonly=True)
    def export_report(self, report_model, options, file_type, context=None, **kwargs):
        if file_type not in EXPORT_TYPES:
            raise BadRequest("Unknown export type")
        registry = request.env.registry
        if report_model not in registry or not issubclass(registry[report_model], registry['ci.account.report']):
            raise BadRequest("Unknown report")
        user_context = json.loads(context) if context else {}
        report_context = {key: user_context[key] for key in ('allowed_company_ids', 'lang', 'tz')
                          if key in user_context}
        report = request.env[report_model].with_context(**report_context)
        method, content_type = EXPORT_TYPES[file_type]
        content, filename = getattr(report, method)(json.loads(options))
        return request.make_response(content, headers=[
            ('Content-Type', content_type),
            ('Content-Length', len(content)),
            ('Content-Disposition', content_disposition(filename)),
        ])
