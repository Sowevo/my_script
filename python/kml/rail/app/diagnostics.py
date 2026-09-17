"""本地轮转日志：关联请求、行程状态和投影判断，不记录 Cookie 或完整几何。"""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time
import uuid

from flask import g, got_request_exception, has_request_context, request


def compact(value):
    if isinstance(value, dict):
        return {str(k): compact(v) for k, v in list(value.items())[:40]}
    if isinstance(value, (list, tuple)):
        result = [compact(v) for v in value[:200]]
        if len(value) > 200:
            result.append({'omitted': len(value) - 200})
        return result
    return value[:1000] if isinstance(value, str) else value


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {'time': self.formatTime(record), 'level': record.levelname,
                **getattr(record, 'event_data', {'message': record.getMessage()})}
        if record.exc_info:
            data['exception'] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def record_diagnostic(event, **fields):
    if has_request_context() and hasattr(g, 'rail_diagnostics'):
        g.rail_diagnostics.append({'event': event, **fields})


def configure_logging(app, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'rail.log'
    handler = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
    handler.setFormatter(JsonFormatter())
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    @app.before_request
    def begin_request():
        g.rail_request_id = uuid.uuid4().hex[:12]
        g.rail_started = time.monotonic()
        g.rail_diagnostics = []

    @app.after_request
    def finish_request(response):
        response.headers['X-Request-ID'] = g.rail_request_id
        if request.path.startswith('/static/') and response.status_code < 400:
            return response
        payload = request.get_json(silent=True) if request.is_json else None
        allowed = {'way_ids', 'way_id', 'point', 'direction', 'revision', 'reset', 'replace_current', 'side', 'source', 'dataset_version'}
        body = {k: v for k, v in payload.items() if k in allowed} if isinstance(payload, dict) else None
        result = response.get_json(silent=True) if response.is_json else None
        summary = {k: result[k] for k in ('error', 'code', 'current_way', 'choices', 'path', 'stop_reason', 'revision', 'dataset_version', 'manual_confirmation_required')
                   if k in result} if isinstance(result, dict) else None
        data = {'event': 'request', 'request_id': g.rail_request_id,
                'method': request.method, 'path': request.path,
                'query': compact(request.args.to_dict(flat=False)), 'body': compact(body),
                'status': response.status_code, 'duration_ms': round((time.monotonic() - g.rail_started) * 1000, 1),
                'result': compact(summary), 'diagnostics': compact(g.rail_diagnostics)}
        app.logger.log(logging.WARNING if response.status_code >= 400 else logging.INFO,
                       'request', extra={'event_data': data})
        return response

    def log_exception(sender, exception, **kwargs):
        app.logger.error('unhandled_exception', extra={'event_data': {
            'event': 'unhandled_exception', 'request_id': getattr(g, 'rail_request_id', None),
            'path': request.path}}, exc_info=(type(exception), exception, exception.__traceback__))

    got_request_exception.connect(log_exception, app, weak=False)
    return path
