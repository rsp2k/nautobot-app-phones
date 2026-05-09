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
router.register("carriers", views.CarrierUIViewSet)
router.register("partitions", views.PartitionUIViewSet)
router.register("calling-search-spaces", views.CallingSearchSpaceUIViewSet)
router.register("directory-numbers", views.DirectoryNumberUIViewSet)
router.register("did-blocks", views.DIDBlockUIViewSet)
router.register("dids", views.DIDUIViewSet)
router.register("phones", views.PhoneUIViewSet)
router.register("trunks", views.TrunkUIViewSet)
router.register("route-lists", views.RouteListUIViewSet)
router.register("route-groups", views.RouteGroupUIViewSet)
router.register("route-patterns", views.RoutePatternUIViewSet)
router.register("translation-patterns", views.TranslationPatternUIViewSet)
router.register("analog-gateways", views.AnalogGatewayUIViewSet)
router.register("hunt-pilots", views.HuntPilotUIViewSet)
router.register("hunt-lists", views.HuntListUIViewSet)
router.register("line-groups", views.LineGroupUIViewSet)
router.register("device-profiles", views.DeviceProfileUIViewSet)
router.register("voicemail-profiles", views.VoicemailProfileUIViewSet)
router.register("call-pickup-groups", views.CallPickupGroupUIViewSet)

urlpatterns = router.urls
