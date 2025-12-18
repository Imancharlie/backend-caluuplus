from rest_framework import viewsets, permissions, status, parsers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.conf import settings
from django.core.mail import send_mail
import logging

from .models import Resource, Opportunity
from .serializers import ResourceSerializer, OpportunitySerializer

logger = logging.getLogger(__name__)


class ResourceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing academic resources.

    Provides CRUD operations for resources with file uploads and university filtering.
    """
    queryset = Resource.objects.all().order_by('-created_at')
    serializer_class = ResourceSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, parsers.JSONParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['university', 'created_by']

    def perform_create(self, serializer):
        """Set the creator when creating a resource."""
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        """Filter resources based on query parameters and user's university."""
        queryset = Resource.objects.all().order_by('-created_at')

        # Filter by user's university (show their university + all universities)
        if self.request.user.is_authenticated:
            try:
                # Get user's university from Student profile
                student_profile = self.request.user.student_profile
                user_university_id = student_profile.university_id

                # Show resources from user's university OR resources for all universities (university is null)
                queryset = queryset.filter(
                    Q(university_id=user_university_id) |
                    Q(university__isnull=True)
                )
            except:
                # User doesn't have a student profile or other error, show only universal resources
                queryset = queryset.filter(university__isnull=True)

        # Additional filter by university if explicitly provided in query params (for admin/staff use)
        university_id = self.request.query_params.get('university')
        if university_id:
            try:
                queryset = queryset.filter(university_id=int(university_id))
            except (ValueError, TypeError):
                pass  # Invalid university ID, ignore filter

        # Filter by file type if provided
        file_type = self.request.query_params.get('file_type')
        if file_type:
            queryset = queryset.filter(file_type=file_type)

        # Search in title and description
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )

        return queryset

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download the resource file."""
        resource = self.get_object()
        if resource.file:
            response = Response()
            response['Content-Disposition'] = f'attachment; filename="{resource.file.name}"'
            response['X-Sendfile'] = resource.file.path
            return response
        return Response({'error': 'No file attached'}, status=status.HTTP_404_NOT_FOUND)


class OpportunityViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing opportunities (seminars, competitions, jobs, etc.).

    Provides CRUD operations with media uploads and comprehensive filtering.
    """
    queryset = Opportunity.objects.all().order_by('-created_at')
    serializer_class = OpportunitySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, parsers.JSONParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['university', 'category', 'created_by']

    def perform_create(self, serializer):
        """Set the creator, status, and is_active when creating an opportunity."""
        # Validate university belongs to user
        university = serializer.validated_data.get('university')
        if university and self.request.user.is_authenticated:
            try:
                student_profile = self.request.user.student_profile
                if student_profile.university_id != university.id:
                    from rest_framework.exceptions import PermissionDenied
                    raise PermissionDenied("You can only create opportunities for your university.")
            except AttributeError:
                pass  # User doesn't have student profile, allow if admin/staff
        
        opportunity = serializer.save(
            created_by=self.request.user,
            status='pending',
            is_active=False
        )
        self._notify_admin_submission(opportunity)

    def get_queryset(self):
        """Filter opportunities based on query parameters."""
        queryset = Opportunity.objects.all()

        # Check if this is a request for user's own opportunities
        created_by_filter = self.request.query_params.get('created_by')
        status_filter = self.request.query_params.get('status')
        
        # If filtering by created_by or status, show all user's opportunities regardless of status
        if created_by_filter or status_filter:
            # User wants to see their own opportunities (My Opportunities page)
            if self.request.user.is_authenticated:
                queryset = queryset.filter(created_by=self.request.user)
        else:
            # For authenticated users: show their own opportunities (all statuses) + approved opportunities from others
            # For anonymous users: only show approved and active opportunities
            if self.request.user.is_authenticated:
                # Show user's own opportunities (any status) OR approved opportunities from others
                queryset = queryset.filter(
                    Q(created_by=self.request.user) |
                    (Q(status='approved') & Q(is_active=True))
                )
            else:
                # Public view - only show approved and active opportunities
                queryset = queryset.filter(status='approved', is_active=True)

        # Filter by university if explicitly provided in query params (for admin/staff use)
        university_id = self.request.query_params.get('university')
        if university_id:
            try:
                queryset = queryset.filter(university_id=university_id)
            except (ValueError, TypeError):
                pass  # Invalid university ID, ignore filter

        # Filter by status if provided (for user's own opportunities)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by category if provided
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            try:
                from datetime import datetime
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(start_date__gte=start_date_obj)
            except (ValueError, TypeError):
                pass  # Invalid date format, ignore filter

        if end_date:
            try:
                from datetime import datetime
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(end_date__lte=end_date_obj)
            except (ValueError, TypeError):
                pass  # Invalid date format, ignore filter

        # Search in title and content
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(content__icontains=search)
            )

        return queryset.order_by('-created_at')
    
    def get_object(self):
        """Override to check permissions for retrieving single opportunity."""
        obj = super().get_object()
        
        # If not active/approved, only allow creator or admin/staff to view
        if obj.status != 'approved' or not obj.is_active:
            if self.request.user.is_authenticated:
                # Allow if user is creator or admin/staff
                if obj.created_by != self.request.user and not (self.request.user.is_staff or self.request.user.is_superuser):
                    from rest_framework.exceptions import NotFound
                    raise NotFound("Opportunity not found.")
            else:
                # Anonymous users can't see non-approved opportunities
                from rest_framework.exceptions import NotFound
                raise NotFound("Opportunity not found.")
        
        return obj
    
    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to use get_object with permission checks."""
        return super().retrieve(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        """Override update to handle status reset and permission checks."""
        instance = self.get_object()
        
        # Check if user owns this opportunity
        if instance.created_by != request.user and not (request.user.is_staff or request.user.is_superuser):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only edit your own opportunities.")
        
        # If opportunity was approved, reset to pending on update
        if instance.status == 'approved':
            # Update status and is_active in the validated data
            response = super().update(request, *args, **kwargs)
            instance.refresh_from_db()
            instance.status = 'pending'
            instance.is_active = False
            instance.save()
            # Return updated serializer with new status
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        
        return super().update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Override destroy to check permissions."""
        instance = self.get_object()
        
        # Check if user owns this opportunity or is admin/staff
        if instance.created_by != request.user and not (request.user.is_staff or request.user.is_superuser):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only delete your own opportunities.")
        
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def download_media(self, request, pk=None):
        """Download the opportunity cover media."""
        opportunity = self.get_object()
        if opportunity.cover_media:
            response = Response()
            response['Content-Disposition'] = f'attachment; filename="{opportunity.cover_media.name}"'
            response['X-Sendfile'] = opportunity.cover_media.path
            return response
        return Response({'error': 'No media attached'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get all available opportunity categories."""
        categories = [
            {'value': choice[0], 'label': choice[1]}
            for choice in Opportunity.CATEGORY_CHOICES
        ]
        return Response(categories)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get statistics about opportunities."""
        queryset = self.get_queryset()

        # Count by category
        category_stats = {}
        for choice in Opportunity.CATEGORY_CHOICES:
            category_stats[choice[0]] = queryset.filter(category=choice[0]).count()

        # Count by university
        university_stats = {}
        for opp in queryset.values('university__name').distinct():
            if opp['university__name']:
                university_stats[opp['university__name']] = queryset.filter(
                    university__name=opp['university__name']
                ).count()

        return Response({
            'total_opportunities': queryset.count(),
            'category_breakdown': category_stats,
            'university_breakdown': university_stats,
        })
    
    @action(detail=True, methods=['post', 'patch'], permission_classes=[permissions.IsAdminUser])
    def approve(self, request, pk=None):
        """
        Admin endpoint to approve an opportunity.
        POST/PATCH /api/resources_opps/opportunities/{id}/approve/
        Body (optional): {"admin_note": "Internal note", "comment": "Message for user"}
        """
        try:
            # For admin actions, bypass get_object permission checks
            # Admin should be able to see all opportunities regardless of status
            opportunity = Opportunity.objects.get(pk=pk)
        except Opportunity.DoesNotExist:
            return Response(
                {'error': f'Opportunity with id {pk} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Error retrieving opportunity: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Optional: admin can provide a note/reason (for internal use)
        admin_note = request.data.get('admin_note', '')
        # Optional: comment to show to the user in notification
        comment = request.data.get('comment', '')
        
        opportunity.status = 'approved'
        opportunity.is_active = True
        opportunity.save()
        
        # Send notification to creator when approved
        if opportunity.created_by:
            try:
                from api.models import Notification
                
                # Build notification message
                title = f"Great News: Your Opportunity Has Been Approved!"
                
                body = f"Congratulations! Your opportunity '{opportunity.title}' has been approved and is now live on the platform. "
                
                # Add comment if provided
                if comment:
                    body += f"\n\n{comment}"
                else:
                    body += "Students can now view and apply for this opportunity. Thank you for contributing to our community!"
                
                # Create notification
                Notification.objects.create(
                    user=opportunity.created_by,
                    title=title,
                    body=body,
                    notification_type='success',
                    link=f'/opportunities/{opportunity.id}' if opportunity.id else None
                )
            except Exception as e:
                # Log error but don't fail the request
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send approval notification: {str(e)}")
        
        serializer = self.get_serializer(opportunity)
        return Response({
            'id': str(opportunity.id),
            'status': opportunity.status,
            'is_active': opportunity.is_active,
            'admin_note': admin_note,
            'comment': comment,
            'message': 'Opportunity approved successfully',
            'notification_sent': bool(opportunity.created_by),
            'opportunity': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post', 'patch'], permission_classes=[permissions.IsAdminUser])
    def reject(self, request, pk=None):
        """
        Admin endpoint to reject an opportunity.
        POST/PATCH /api/resources_opps/opportunities/{id}/reject/
        Body (optional): {"rejection_reason": "Reason for rejection", "comment": "Additional comment for user"}
        """
        try:
            # For admin actions, bypass get_object permission checks
            opportunity = Opportunity.objects.get(pk=pk)
        except Opportunity.DoesNotExist:
            return Response(
                {'error': f'Opportunity with id {pk} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Error retrieving opportunity: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Optional: admin can provide a rejection reason (for internal use)
        rejection_reason = request.data.get('rejection_reason', '')
        # Optional: comment to show to the user in notification
        comment = request.data.get('comment', '')
        
        opportunity.status = 'rejected'
        opportunity.is_active = False
        opportunity.save()
        
        # Send notification to creator
        if opportunity.created_by:
            try:
                from api.models import Notification
                
                # Build polite notification message
                title = f"Opportunity Update: {opportunity.title}"
                
                # Base message
                body = f"Thank you for submitting your opportunity '{opportunity.title}'. "
                body += "After careful review, we're unable to approve it at this time. "
                
                # Add comment if provided
                if comment:
                    body += f"\n\nNote: {comment}"
                else:
                    body += "If you have any questions or would like to resubmit with modifications, please don't hesitate to reach out to our support team."
                
                body += "\n\nWe appreciate your understanding and look forward to your future submissions."
                
                # Create notification
                Notification.objects.create(
                    user=opportunity.created_by,
                    title=title,
                    body=body,
                    notification_type='info',
                    link=f'/opportunities/{opportunity.id}' if opportunity.id else None
                )
            except Exception as e:
                # Log error but don't fail the request
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send rejection notification: {str(e)}")
        
        serializer = self.get_serializer(opportunity)
        return Response({
            'id': str(opportunity.id),
            'status': opportunity.status,
            'is_active': opportunity.is_active,
            'rejection_reason': rejection_reason,
            'comment': comment,
            'message': 'Opportunity rejected successfully',
            'notification_sent': bool(opportunity.created_by),
            'opportunity': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post', 'patch'], permission_classes=[permissions.IsAdminUser])
    def set_status(self, request, pk=None):
        """
        Admin endpoint to set opportunity status (approve/reject/pending).
        POST/PATCH /api/resources_opps/opportunities/{id}/set_status/
        Body: {"status": "approved|rejected|pending", "is_active": true|false (optional)}
        """
        try:
            # For admin actions, bypass get_object permission checks
            opportunity = Opportunity.objects.get(pk=pk)
        except Opportunity.DoesNotExist:
            return Response(
                {'error': f'Opportunity with id {pk} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Error retrieving opportunity: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        new_status = request.data.get('status')
        is_active = request.data.get('is_active')
        
        if new_status not in ['approved', 'rejected', 'pending']:
            return Response(
                {'error': 'status must be "approved", "rejected", or "pending"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        opportunity.status = new_status
        
        # Set is_active based on status if not explicitly provided
        if is_active is not None:
            opportunity.is_active = is_active
        else:
            opportunity.is_active = (new_status == 'approved')
        
        opportunity.save()
        
        serializer = self.get_serializer(opportunity)
        return Response({
            'id': str(opportunity.id),
            'status': opportunity.status,
            'is_active': opportunity.is_active,
            'message': f'Opportunity status set to {new_status}',
            'opportunity': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAdminUser])
    def pending(self, request):
        """
        Get all pending opportunities for admin review.
        GET /api/resources_opps/opportunities/pending/
        Query params: ?university={id}&category={category}&search={query}&page={page}&page_size={size}
        """
        queryset = Opportunity.objects.filter(status='pending').order_by('-created_at')
        
        # Filter by university if provided
        university_id = request.query_params.get('university')
        if university_id:
            try:
                queryset = queryset.filter(university_id=university_id)
            except (ValueError, TypeError):
                pass
        
        # Filter by category if provided
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Search in title and content
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(content__icontains=search)
            )
        
        # Pagination
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        page_size = request.query_params.get('page_size', 20)
        try:
            paginator.page_size = int(page_size)
        except (ValueError, TypeError):
            paginator.page_size = 20
        
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'results': serializer.data
        })
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAdminUser])
    def all_statuses(self, request):
        """
        Get all opportunities with any status (for admin management).
        GET /api/resources_opps/opportunities/all_statuses/
        Query params: ?status={pending|approved|rejected}&university={id}&category={category}&search={query}
        """
        queryset = Opportunity.objects.all().order_by('-created_at')
        
        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by university if provided
        university_id = request.query_params.get('university')
        if university_id:
            try:
                queryset = queryset.filter(university_id=university_id)
            except (ValueError, TypeError):
                pass
        
        # Filter by category if provided
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Search in title and content
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(content__icontains=search)
            )
        
        # Pagination
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        page_size = request.query_params.get('page_size', 20)
        try:
            paginator.page_size = int(page_size)
        except (ValueError, TypeError):
            paginator.page_size = 20
        
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'results': serializer.data
        })
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def bulk_approve(self, request):
        """
        Bulk approve multiple opportunities.
        POST /api/resources_opps/opportunities/bulk_approve/
        Body: {"opportunity_ids": ["id1", "id2", ...]}
        """
        opportunity_ids = request.data.get('opportunity_ids', [])
        
        if not opportunity_ids or not isinstance(opportunity_ids, list):
            return Response(
                {'error': 'opportunity_ids must be a non-empty array'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        opportunities = Opportunity.objects.filter(id__in=opportunity_ids)
        updated_count = opportunities.update(status='approved', is_active=True)
        
        return Response({
            'message': f'Successfully approved {updated_count} opportunity(ies)',
            'approved_count': updated_count,
            'total_requested': len(opportunity_ids)
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def bulk_reject(self, request):
        """
        Bulk reject multiple opportunities.
        POST /api/resources_opps/opportunities/bulk_reject/
        Body: {"opportunity_ids": ["id1", "id2", ...], "rejection_reason": "Reason (optional)"}
        """
        opportunity_ids = request.data.get('opportunity_ids', [])
        rejection_reason = request.data.get('rejection_reason', '')
        
        if not opportunity_ids or not isinstance(opportunity_ids, list):
            return Response(
                {'error': 'opportunity_ids must be a non-empty array'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        opportunities = Opportunity.objects.filter(id__in=opportunity_ids)
        updated_count = opportunities.update(status='rejected', is_active=False)
        
        return Response({
            'message': f'Successfully rejected {updated_count} opportunity(ies)',
            'rejected_count': updated_count,
            'total_requested': len(opportunity_ids),
            'rejection_reason': rejection_reason
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAdminUser])
    def list_ids(self, request):
        """
        Get list of all opportunity IDs (for debugging/admin use).
        GET /api/resources_opps/opportunities/list_ids/
        Query params: ?status={pending|approved|rejected}
        """
        queryset = Opportunity.objects.all()
        
        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        opportunity_ids = list(queryset.values_list('id', flat=True))
        
        return Response({
            'count': len(opportunity_ids),
            'opportunity_ids': opportunity_ids,
            'message': 'Use these IDs to test approve/reject endpoints'
        })
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAdminUser])
    def admin_stats(self, request):
        """
        Get admin statistics for opportunities management.
        GET /api/resources_opps/opportunities/admin_stats/
        """
        total = Opportunity.objects.count()
        pending = Opportunity.objects.filter(status='pending').count()
        approved = Opportunity.objects.filter(status='approved', is_active=True).count()
        rejected = Opportunity.objects.filter(status='rejected').count()
        
        # Count by category
        category_stats = {}
        for choice in Opportunity.CATEGORY_CHOICES:
            category_stats[choice[0]] = {
                'label': choice[1],
                'total': Opportunity.objects.filter(category=choice[0]).count(),
                'pending': Opportunity.objects.filter(category=choice[0], status='pending').count(),
                'approved': Opportunity.objects.filter(category=choice[0], status='approved', is_active=True).count(),
                'rejected': Opportunity.objects.filter(category=choice[0], status='rejected').count(),
            }
        
        # Count by status
        status_breakdown = {
            'pending': pending,
            'approved': approved,
            'rejected': rejected,
        }
        
        # Recent pending (last 7 days)
        from django.utils import timezone
        from datetime import timedelta
        recent_pending = Opportunity.objects.filter(
            status='pending',
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count()
        
        return Response({
            'total_opportunities': total,
            'status_breakdown': status_breakdown,
            'category_breakdown': category_stats,
            'recent_pending_7_days': recent_pending,
            'pending_percentage': round((pending / total * 100) if total > 0 else 0, 2),
            'approval_rate': round((approved / total * 100) if total > 0 else 0, 2),
        })

    def _notify_admin_submission(self, opportunity):
        """Notify administrators when a new opportunity requires approval."""
        from api.models import User, Notification
        from django.db import models
        
        # Send in-app notification to all admin/superuser accounts
        try:
            admin_users = User.objects.filter(
                models.Q(is_superuser=True) | models.Q(is_staff=True)
            ).distinct()
            
            if not admin_users.exists():
                return  # No admins to notify
            
            opportunity_title = opportunity.title
            submitted_by = getattr(opportunity.created_by, 'display_name', 'Unknown user') if opportunity.created_by else 'Unknown user'
            submitted_by_email = getattr(opportunity.created_by, 'email', 'Unknown') if opportunity.created_by else 'Unknown'
            
            # Get category display name (Django automatically provides get_FOO_display() for choice fields)
            try:
                category = opportunity.get_category_display()
            except AttributeError:
                category = dict(Opportunity.CATEGORY_CHOICES).get(opportunity.category, opportunity.category)
            
            university_name = opportunity.university.name if opportunity.university else "All Universities"
            
            title = "New Opportunity Awaiting Approval"
            body = f"A new opportunity has been submitted and requires your approval.\n\n"
            body += f"Title: {opportunity_title}\n"
            body += f"Category: {category}\n"
            body += f"University: {university_name}\n"
            body += f"Submitted by: {submitted_by} ({submitted_by_email})\n\n"
            body += "Please review and approve or reject this opportunity."
            
            # Create notification link (adjust path as needed)
            notification_link = f"/opportunities/{opportunity.id}" if opportunity.id else None
            
            for admin in admin_users:
                try:
                    Notification.objects.create(
                        user=admin,
                        title=title,
                        body=body,
                        notification_type='info',
                        link=notification_link
                    )
                except Exception as e:
                    logger.error(f"Failed to create notification for admin {admin.email}: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to send in-app notifications for opportunity submission: {str(e)}")
        
        # Also send email notification if configured
        admin_email = getattr(settings, 'OPPORTUNITY_REVIEW_NOTIFY_EMAIL', None)
        review_url = getattr(settings, 'OPPORTUNITY_ADMIN_REVIEW_URL', '')
        if admin_email:
            subject = "New Opportunity Awaiting Approval"
            body_lines = [
                "Hello admin team,",
                "",
                "A new opportunity has been submitted and is pending approval.",
                f"Title: {opportunity.title}",
                f"Submitted by: {getattr(opportunity.created_by, 'email', 'Unknown user') if opportunity.created_by else 'Unknown'}",
                "",
                "You can review and approve it using the link below:",
                review_url,
            ]

            try:
                send_mail(
                    subject,
                    "\n".join(body_lines),
                    getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@caluuplus.com'),
                    [admin_email],
                    fail_silently=False,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to send opportunity submission email: %s", exc)
