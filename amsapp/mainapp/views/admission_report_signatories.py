from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import AdmissionReportSignatory, FacultyDepartment
from ..permissions import require_menu_permission
from ..serializers.admission_report_signatory import AdmissionReportSignatorySerializer
from ..services.access_control import get_user_access_scope


MENU_LINK = "/report-signatories"


def _custom_user(request):
    return getattr(request.user, "custom_user", request.user)


def _accessible_signatories(request):
    queryset = AdmissionReportSignatory.objects.select_related(
        "department", "faculty", "affiliation_department"
    )
    scope = get_user_access_scope(_custom_user(request))
    if scope["is_global"]:
        return queryset

    department_ids = scope["department_ids"] or []
    if not department_ids:
        return queryset.none()
    faculty_ids = FacultyDepartment.objects.filter(
        department_ids__overlap=department_ids
    ).values_list("faculty_id", flat=True)
    return queryset.filter(
        Q(department_id__in=department_ids) | Q(faculty_id__in=faculty_ids)
    )


def _target_is_accessible(request, department_id=None, faculty_id=None):
    scope = get_user_access_scope(_custom_user(request))
    if scope["is_global"]:
        return True
    department_ids = scope["department_ids"] or []
    if department_id:
        return int(department_id) in department_ids
    if faculty_id:
        return FacultyDepartment.objects.filter(
            faculty_id=faculty_id,
            department_ids__overlap=department_ids,
        ).exists()
    return False


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def admission_report_signatories(request):
    # Every authenticated results user may read the scoped names so PDF export
    # works even when the configuration menu is not assigned to their role.
    # Creating/updating the configuration still requires menu write access.
    if request.method != "GET":
        denied = require_menu_permission(
            request,
            MENU_LINK,
            "write",
            "You do not have permission to manage report signatories.",
        )
        if denied:
            return denied

    if request.method == "GET":
        queryset = _accessible_signatories(request)
        department_id = request.query_params.get("department_id")
        faculty_id = request.query_params.get("faculty_id")
        if department_id:
            queryset = queryset.filter(
                Q(department_id=department_id) | Q(role=AdmissionReportSignatory.ROLE_DEAN)
            )
        if faculty_id:
            queryset = queryset.filter(
                Q(faculty_id=faculty_id)
                | Q(role__in=[
                    AdmissionReportSignatory.ROLE_CONVENOR,
                    AdmissionReportSignatory.ROLE_DEPARTMENT_HEAD,
                ])
            )
        return Response(
            {
                "success": True,
                "data": AdmissionReportSignatorySerializer(queryset, many=True).data,
            }
        )

    role = str(request.data.get("role") or "").upper()
    department_id = request.data.get("department")
    faculty_id = request.data.get("faculty")
    if not _target_is_accessible(
        request,
        department_id=department_id,
        faculty_id=faculty_id,
    ):
        return Response(
            {"success": False, "message": "You do not have access to this mapping."},
            status=status.HTTP_403_FORBIDDEN,
        )

    lookup = {"role": role}
    if role == AdmissionReportSignatory.ROLE_DEAN:
        lookup["faculty_id"] = faculty_id
    else:
        lookup["department_id"] = department_id
    existing = AdmissionReportSignatory.objects.filter(**lookup).first()
    serializer = AdmissionReportSignatorySerializer(existing, data=request.data)
    serializer.is_valid(raise_exception=True)
    signatory = serializer.save()
    return Response(
        {
            "success": True,
            "data": AdmissionReportSignatorySerializer(signatory).data,
            "message": "Report signatory saved successfully.",
        },
        status=status.HTTP_200_OK if existing else status.HTTP_201_CREATED,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def admission_report_signatory_detail(request, signatory_id):
    denied = require_menu_permission(
        request,
        MENU_LINK,
        "delete",
        "You do not have permission to remove report signatories.",
    )
    if denied:
        return denied
    signatory = _accessible_signatories(request).filter(id=signatory_id).first()
    if not signatory:
        return Response(
            {"success": False, "message": "Report signatory not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    signatory.delete()
    return Response({"success": True, "message": "Report signatory removed."})
