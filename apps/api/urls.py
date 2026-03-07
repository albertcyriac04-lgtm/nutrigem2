from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserProfileViewSet, FoodItemViewSet,
    ConsumptionLogViewSet, WeightRecordViewSet
)

router = DefaultRouter()
router.register(r'profiles', UserProfileViewSet, basename='profile')
router.register(r'food-items', FoodItemViewSet, basename='food-item')
router.register(r'consumption-logs', ConsumptionLogViewSet, basename='consumption-log')
router.register(r'weight-records', WeightRecordViewSet, basename='weight-record')

urlpatterns = [
    path('', include(router.urls)),
]


