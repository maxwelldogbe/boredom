"""django.contrib.admin, with the Boredom dashboard site as the default `admin.site`."""

from django.contrib.admin.apps import AdminConfig


class BoredomAdminConfig(AdminConfig):
    default_site = "analytics.admin_site.BoredomAdminSite"
