"""URL routes for nautobot-app-phones.

Plugin URLs auto-mount under /plugins/<base_url>/ — `base_url='phones'`
in our AppConfig means routes here resolve under `/plugins/phones/`.
NautobotUIViewSetRouter handles list/detail/create/edit/delete URL
generation per registered viewset.
"""

from nautobot.apps.urls import NautobotUIViewSetRouter

from nautobot_phones import views

app_name = "nautobot_phones"

router = NautobotUIViewSetRouter()
router.register("phone-systems", views.PhoneSystemUIViewSet)

urlpatterns = router.urls
