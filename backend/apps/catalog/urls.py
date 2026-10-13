from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("units", views.UnitViewSet, basename="unit")
router.register("suppliers", views.SupplierViewSet, basename="supplier")
router.register("products", views.ProductViewSet, basename="product")
urlpatterns = router.urls
