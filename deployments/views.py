from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAdminUser

from .models import Deployment
from .serializers import DeploymentDetailSerializer, DeploymentSerializer


class DeploymentListView(ListAPIView):
    """Admin-only history of automated deployments, newest first."""

    queryset = Deployment.objects.all()
    serializer_class = DeploymentSerializer
    permission_classes = [IsAdminUser]


class DeploymentDetailView(RetrieveAPIView):
    """Admin-only detail (incl. full log) of one deployment."""

    queryset = Deployment.objects.all()
    serializer_class = DeploymentDetailSerializer
    permission_classes = [IsAdminUser]