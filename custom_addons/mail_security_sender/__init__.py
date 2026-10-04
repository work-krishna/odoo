from . import models


def _post_init_hook(env):
    env['mail.template']._security_sender_sync_templates()


def _uninstall_hook(env):
    env['mail.template']._security_sender_sync_templates(enable=False)
