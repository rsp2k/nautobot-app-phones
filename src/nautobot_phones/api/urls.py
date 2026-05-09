"""URL routes for the nautobot-app-phones REST API.

Auto-mounted under /api/plugins/<base_url>/ — `base_url='phones'` in our
AppConfig means routes here resolve under `/api/plugins/phones/`.
"""

from nautobot.apps.api import OrderedDefaultRouter

from nautobot_phones.api import views

router = OrderedDefaultRouter()
router.register("phone-systems", views.PhoneSystemAPIViewSet)
router.register("carriers", views.CarrierAPIViewSet)
router.register("partitions", views.PartitionAPIViewSet)
router.register("calling-search-spaces", views.CallingSearchSpaceAPIViewSet)
router.register("css-partition-memberships", views.CSSPartitionMembershipAPIViewSet)
router.register("directory-numbers", views.DirectoryNumberAPIViewSet)
router.register("did-blocks", views.DIDBlockAPIViewSet)
router.register("dids", views.DIDAPIViewSet)
router.register("did-assignments", views.DIDAssignmentAPIViewSet)
router.register("phones", views.PhoneAPIViewSet)
router.register("lines", views.LineAPIViewSet)
router.register("busy-lamp-fields", views.BusyLampFieldAPIViewSet)
router.register("trunks", views.TrunkAPIViewSet)
router.register("route-lists", views.RouteListAPIViewSet)
router.register("route-list-members", views.RouteListMemberAPIViewSet)
router.register("route-groups", views.RouteGroupAPIViewSet)
router.register("route-group-members", views.RouteGroupMemberAPIViewSet)
router.register("route-patterns", views.RoutePatternAPIViewSet)
router.register("translation-patterns", views.TranslationPatternAPIViewSet)
router.register("analog-gateways", views.AnalogGatewayAPIViewSet)
router.register("analog-ports", views.AnalogPortAPIViewSet)
router.register("hunt-pilots", views.HuntPilotAPIViewSet)
router.register("hunt-lists", views.HuntListAPIViewSet)
router.register("hunt-list-members", views.HuntListMemberAPIViewSet)
router.register("line-groups", views.LineGroupAPIViewSet)
router.register("line-group-members", views.LineGroupMemberAPIViewSet)

app_name = "nautobot_phones-api"
urlpatterns = router.urls
