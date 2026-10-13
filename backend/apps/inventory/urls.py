from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("stock", views.StockBalanceViewSet, basename="stock")
router.register("movements", views.StockMovementViewSet, basename="movement")
router.register("adjustments", views.AdjustmentViewSet, basename="adjustment")
router.register("transfers", views.TransferViewSet, basename="transfer")
urlpatterns = router.urls
