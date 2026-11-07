from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from ..models import AdmissionConfiguration, AdmissionResult, Department, Exam, VivaAssignment
from ..models.viva_marks import VivaMarks
from ..utils import normalize_semester_value


class AdmissionConfigurationSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.department_name", read_only=True)
    department_shortname = serializers.CharField(
        source="department.department_shortname",
        read_only=True,
    )
    exam_department = serializers.CharField(source="exam.department", read_only=True)

    class Meta:
        model = AdmissionConfiguration
        fields = [
            "id",
            "department",
            "department_name",
            "department_shortname",
            "semester",
            "exam",
            "exam_department",
            "seat_limit",
            "waiting_student_limit",
            "threshold",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_threshold(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Threshold must be between 0 and 100")
        return value

    def validate_semester(self, value):
        try:
            return normalize_semester_value(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))


class AdmissionConfigurationUpsertSerializer(serializers.Serializer):
    department_id = serializers.IntegerField(required=False)
    exam_id = serializers.IntegerField(required=False)
    semester = serializers.CharField(required=False)
    seat_limit = serializers.IntegerField(required=False, min_value=0)
    waiting_student_limit = serializers.IntegerField(required=False, min_value=0)
    threshold = serializers.FloatField(required=False, min_value=0.0, max_value=100.0)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        exam_id = attrs.get("exam_id")
        department_id = attrs.get("department_id")
        semester = attrs.get("semester")

        if semester is not None:
            try:
                attrs["semester"] = normalize_semester_value(semester)
            except ValueError as exc:
                raise serializers.ValidationError({"semester": str(exc)})

        if self.partial:
            if exam_id and not Exam.objects.filter(id=exam_id).exists():
                raise serializers.ValidationError({"exam_id": "Exam does not exist"})
            if department_id and not Department.objects.filter(id=department_id).exists():
                raise serializers.ValidationError({"department_id": "Department does not exist"})
            return attrs

        if not exam_id and not (department_id and semester):
            raise serializers.ValidationError(
                "Provide exam_id or both department_id and semester."
            )

        if exam_id and not Exam.objects.filter(id=exam_id).exists():
            raise serializers.ValidationError({"exam_id": "Exam does not exist"})

        if department_id and not Department.objects.filter(id=department_id).exists():
            raise serializers.ValidationError({"department_id": "Department does not exist"})

        return attrs


class AdmissionResultSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source="student.username", read_only=True)
    student_full_name = serializers.CharField(source="student.full_name", read_only=True)
    student_f_id = serializers.CharField(source="student.f_id", read_only=True)
    student_registration_semester = serializers.CharField(
        source="student.registration_semester",
        read_only=True,
    )
    student_ssc = serializers.FloatField(source="student.ssc", read_only=True)
    student_academic_type = serializers.CharField(
        source="student.academic_type",
        read_only=True,
    )
    student_hsc = serializers.FloatField(source="student.hsc", read_only=True)
    student_diploma = serializers.FloatField(source="student.diploma", read_only=True)
    department_name = serializers.CharField(source="department.department_name", read_only=True)
    department_shortname = serializers.CharField(
        source="department.department_shortname",
        read_only=True,
    )
    configuration_details = AdmissionConfigurationSerializer(
        source="configuration",
        read_only=True,
    )
    exam_details = serializers.SerializerMethodField()
    viva_marks_entered = serializers.SerializerMethodField()
    # Denominators for the "obtained out of total" display on the results board.
    # Reuse the scorer's own totals so UI matches the weighted calculation.
    written_total_marks = serializers.SerializerMethodField()
    viva_total_marks = serializers.SerializerMethodField()
    # Populated from the queryset annotation in get_admission_results; null when
    # the student never submitted (absent).
    exam_taken_at = serializers.DateTimeField(read_only=True)
    student_department_choices = serializers.SerializerMethodField()
    eligible_departments = serializers.SerializerMethodField()
    allocated_department = serializers.SerializerMethodField()
    waiting_for = serializers.SerializerMethodField()

    class Meta:
        model = AdmissionResult
        fields = [
            "id",
            "exam",
            "student",
            "student_username",
            "student_full_name",
            "student_f_id",
            "student_registration_semester",
            "student_ssc",
            "student_academic_type",
            "student_hsc",
            "student_diploma",
            "configuration",
            "configuration_details",
            "department",
            "department_name",
            "department_shortname",
            "allocated_department",
            "waiting_department",
            "mcq_marks",
            "viva_marks",
            "viva_marks_entered",
            "viva_given",
            "written_total_marks",
            "viva_total_marks",
            "written_viva_total",
            "total_marks",
            "weighted_total_marks",
            "attended_exam",
            "subject_wise_marks",
            "is_selected",
            "is_override_accepted",
            "is_admitted",
            "result_status",
            "status",
            "threshold_applied",
            "remarks",
            "ssc_score",
            "academic_score",
            "academic_source",
            "ssc_contribution",
            "academic_contribution",
            "written_contribution",
            "viva_contribution",
            "exam_details",
            "exam_taken_at",
            "student_department_choices",
            "eligible_departments",
            "waiting_for",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "waiting_department",
            "exam_taken_at",
            "written_total_marks",
            "viva_total_marks",
            "created_at",
            "updated_at",
            "total_marks",
            "written_viva_total",
            "weighted_total_marks",
        ]

    @extend_schema_field(serializers.DictField())
    def get_exam_details(self, obj):
        department_label = (obj.exam.department or "").strip()
        stored_exam_type = (getattr(obj.exam, "exam_type", "") or "").upper()
        is_central = (
            stored_exam_type == "CENTRAL"
            or department_label.casefold() == "central"
            or department_label.casefold().startswith("central (")
        )
        return {
            "id": obj.exam.id,
            "department": obj.exam.department,
            "semester": obj.exam.semester,
            "total_marks": obj.exam.total_marks,
            "exam_type": "CENTRAL" if is_central else "SCHEDULED",
        }

    @extend_schema_field(serializers.BooleanField())
    def get_viva_marks_entered(self, obj):
        viva_assignment = (
            VivaAssignment.objects.filter(student=obj.student, exam=obj.exam)
            .order_by("-updated_at", "-created_at", "-id")
            .first()
        )
        if viva_assignment:
            return bool(
                viva_assignment.rubric_scores
                or viva_assignment.remarks
                or float(viva_assignment.total_marks or 0) != 0
                or VivaMarks.objects.filter(student=obj.student).exists()
            )

        return VivaMarks.objects.filter(student=obj.student).exists()

    @extend_schema_field(serializers.FloatField())
    def get_written_total_marks(self, obj):
        # Lazy import avoids a serializer <-> services import cycle.
        from ..services.admission_calculator import get_written_total_marks_for_exam

        cache = self.context.setdefault("_written_total", {})
        if obj.exam_id not in cache:
            cache[obj.exam_id] = get_written_total_marks_for_exam(obj.exam)
        return cache[obj.exam_id]

    @extend_schema_field(serializers.FloatField())
    def get_viva_total_marks(self, obj):
        from ..services.admission_calculator import get_viva_total_marks_for_student_exam

        return get_viva_total_marks_for_student_exam(obj.student, obj.exam)

    @extend_schema_field(serializers.ListField())
    def get_student_department_choices(self, obj):
        from ..services.admission_calculator import get_effective_department_choices

        choices = get_effective_department_choices(
            student=obj.student,
            exam=obj.exam,
            result=obj,
            fallback_department=obj.department,
        )
        dept_ids = [choice["department_id"] for choice in choices]
        from ..models import Department
        dept_map = {d.id: d.department_shortname for d in Department.objects.filter(id__in=dept_ids)}

        return [
            {
                "department_id": choice["department_id"],
                "department_shortname": dept_map.get(
                    choice["department_id"], f"Dept #{choice['department_id']}"
                ),
                "priority": choice["priority"],
            }
            for choice in choices
        ]

    @extend_schema_field(serializers.ListField())
    def get_eligible_departments(self, obj):
        if not obj.attended_exam:
            return []

        score = obj.weighted_total_marks if obj.weighted_total_marks is not None else obj.total_marks
        if score is None:
            return []
        score = float(score)

        semester = None
        if obj.exam and obj.exam.semester:
            semester = obj.exam.semester
        elif obj.student and obj.student.registration_semester:
            semester = obj.student.registration_semester

        cache = self.context.setdefault("_dept_threshold_map", {})
        if semester and semester not in cache:
            from django.db.models import Q
            from ..models import DepartmentThreshold

            norm_sem = normalize_semester_value(semester) if semester else semester
            thresholds = DepartmentThreshold.objects.filter(
                Q(semester__iexact=semester) | Q(semester__iexact=norm_sem)
            ).select_related("department")
            sem_map = {}
            for t in thresholds:
                if t.department_id and t.min_threshold_mark is not None:
                    sem_map[t.department_id] = float(t.min_threshold_mark)
                    if t.department and t.department.department_shortname:
                        sem_map[t.department.department_shortname.upper()] = float(t.min_threshold_mark)
            cache[semester] = sem_map

        sem_thresholds = cache.get(semester, {}) if semester else {}

        eligible = []
        from ..services.admission_calculator import get_effective_department_choices

        choices = get_effective_department_choices(
            student=obj.student,
            exam=obj.exam,
            result=obj,
            fallback_department=obj.department,
        )

        dept_cache = self.context.setdefault("_all_depts_map", None)
        if dept_cache is None:
            from ..models import Department

            dept_cache = {d.id: d.department_shortname for d in Department.objects.all()}
            self.context["_all_depts_map"] = dept_cache

        if choices:
            for c in choices:
                d_id = c.get("department_id")
                d_short = dept_cache.get(d_id)
                if not d_short and d_id:
                    d_short = f"Dept #{d_id}"

                min_mark = sem_thresholds.get(d_id)
                if min_mark is None and d_short:
                    min_mark = sem_thresholds.get(d_short.upper())

                if min_mark is not None:
                    if score >= min_mark - 0.0001:
                        if d_short and d_short not in eligible:
                            eligible.append(d_short)
                else:
                    applied = float(obj.threshold_applied) if obj.threshold_applied is not None else 0.0
                    if score >= applied - 0.0001 and (obj.is_selected or obj.result_status in ("SELECTED", "WAITING")):
                        if d_short and d_short not in eligible:
                            eligible.append(d_short)
        else:
            target_short = None
            target_id = None
            if obj.department:
                target_short = obj.department.department_shortname
                target_id = obj.department.id
            elif obj.student and obj.student.department_shortname:
                target_short = obj.student.department_shortname

            if target_short:
                min_mark = sem_thresholds.get(target_id) or sem_thresholds.get(target_short.upper())
                if min_mark is not None:
                    if score >= min_mark - 0.0001:
                        eligible.append(target_short)
                elif obj.is_selected or (obj.threshold_applied and score >= float(obj.threshold_applied) - 0.0001):
                    eligible.append(target_short)

        if obj.is_selected and obj.department and obj.department.department_shortname:
            if obj.department.department_shortname not in eligible:
                eligible.insert(0, obj.department.department_shortname)

        return eligible

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_allocated_department(self, obj):
        if obj.is_selected or obj.is_admitted or obj.result_status == "SELECTED":
            return obj.department.department_shortname if obj.department else None
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_waiting_for(self, obj):
        if obj.waiting_department:
            return obj.waiting_department.department_shortname

        # Backward-compatible display for WAITING rows created before the
        # persisted waiting_department field was introduced.
        if obj.result_status == "WAITING":
            if obj.department and obj.department.department_shortname:
                return obj.department.department_shortname
            eligible = self.get_eligible_departments(obj)
            if eligible:
                return eligible[0]
            return "Waiting List"

        return None


class CalculateAdmissionResultsSerializer(serializers.Serializer):
    exam_id = serializers.IntegerField(help_text="Exam ID for which to calculate admission results")

    def validate_exam_id(self, value):
        if not Exam.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Exam with ID {value} does not exist")
        return value


class CalculateResultsResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    processed_count = serializers.IntegerField()
    selected_count = serializers.IntegerField()
    not_selected_count = serializers.IntegerField()
    exam_id = serializers.IntegerField()
    configuration_id = serializers.IntegerField(required=False)
    status_counts = serializers.DictField(required=False)


class AdmissionResultFilterSerializer(serializers.Serializer):
    exam_id = serializers.IntegerField(required=False)
    configuration_id = serializers.IntegerField(required=False)
    department_id = serializers.IntegerField(required=False)
    student_id = serializers.IntegerField(required=False)
    semester = serializers.CharField(required=False)
    search = serializers.CharField(required=False)
    is_selected = serializers.BooleanField(required=False)
    attended_exam = serializers.BooleanField(required=False)
    status = serializers.ChoiceField(
        choices=["PENDING", "PUBLISHED", "CANCELLED"],
        required=False,
    )
    result_status = serializers.ChoiceField(
        choices=["SELECTED", "WAITING", "REJECTED", "ABSENT"],
        required=False,
    )
    sort_by = serializers.ChoiceField(
        choices=["name", "score", "form_id", "serial"],
        required=False,
    )
    order = serializers.ChoiceField(
        choices=["asc", "desc"],
        required=False,
    )


class BulkAdmissionStatusUpdateSerializer(serializers.Serializer):
    configuration_id = serializers.IntegerField(required=False)
    exam_id = serializers.IntegerField(required=False)
    action = serializers.ChoiceField(
        choices=["SET_STATUS", "SET_ADMITTED", "REVERT_TO_STORED_STATUS"],
        required=False,
        default="SET_STATUS",
    )
    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
    )
    result_status = serializers.ChoiceField(
        choices=["SELECTED", "WAITING", "REJECTED"],
        required=False,
    )

    def validate(self, attrs):
        if not attrs.get("configuration_id") and not attrs.get("exam_id"):
            raise serializers.ValidationError(
                "Provide configuration_id or exam_id to update candidate status."
            )

        if attrs.get("action", "SET_STATUS") == "SET_STATUS" and not attrs.get("result_status"):
            raise serializers.ValidationError(
                {"result_status": "result_status is required when action is SET_STATUS."}
            )
        return attrs
