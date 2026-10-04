{
    'name': 'Security Emails Sender',
    'version': '19.0.1.0.0',
    'summary': "Send each company's account-security emails from a dedicated address",
    'description': """
Gives every company a "Security Emails From" address (e.g. support@...). Sign-up
codes, invitations, password resets, two-factor codes and "Security Update"
alerts are then sent from that address instead of the company email, so they
can go out through their own mailbox and outgoing mail server. A company that
leaves it empty keeps sending these emails from its company email.
""",
    'category': 'Productivity/Discuss',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['auth_signup'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': '_post_init_hook',
    'uninstall_hook': '_uninstall_hook',
    'installable': True,
}
