from rest_framework import serializers
from ..models import MarksDistribution, Department, Faculty


def validate_percentage(value, label):
    if value < 0:
        raise serializers.ValidationError(f"{label} cannot be negative")
    if value > 100:
        raise serializers.ValidationError(f"{label} cannot be greater than 100")
    return value


def normalize_shared_academic_weight(serializer, data):
    instance = getattr(serializer, 'instance', None)

    academic_weight = data.get('hsc')
    if academic_weight is None:
        academic_weight = data.get('diploma')
    if academic_weight is None and instance is not None:
        academic_weight = instance.hsc
    if academic_weight is None:
        academic_weight = 0

    data['hsc'] = academic_weight
    data['diploma'] = academic_weight

    ssc = data.get('ssc', instance.ssc if instance is not None else 0)
    main_marks = data.get('main_marks', instance.main_marks if instance is not None else 0)
    viva_marks = data.get('viva_marks', instance.viva_marks if instance is not None else 0)
    total = ssc + academic_weight + main_marks + viva_marks

    if total != 100:
        raise serializers.ValidationError(
            "Total marks distribution must equal 100%: SSC + HSC/Diploma + Main Marks + Viva Marks"
        )

    return data


class MarksDistributionSerializer(serializers.ModelSerializer):
    """Serializer for MarksDistribution model"""
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_shortname = serializers.CharField(source='department.department_shortname', read_only=True)
    faculty_name = serializers.CharField(source='faculty.faculty_name', read_only=True)
    faculty_code = serializers.CharField(source='faculty.faculty_code', read_only=True)
    
    class Meta:
        model = MarksDistribution
        fields = [
            'id', 'department', 'department_name', 'department_shortname',
            'faculty', 'faculty_name', 'faculty_code',
            'ssc', 'hsc', 'diploma', 'main_marks', 'viva_marks'
        ]
        read_only_fields = ['id']

    def validate_ssc(self, value):
        return validate_percentage(value, "SSC marks")

    def validate_hsc(self, value):
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_diploma(self, value):
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_main_marks(self, value):
        return validate_percentage(value, "Main Marks")

    def validate_viva_marks(self, value):
        return validate_percentage(value, "Viva marks")


class MarksDistributionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating MarksDistribution"""
    
    class Meta:
        model = MarksDistribution
        fields = ['faculty', 'department', 'ssc', 'hsc', 'diploma', 'main_marks', 'viva_marks']
        extra_kwargs = {
            'faculty': {'required': False, 'allow_null': True},
            'department': {'required': False, 'allow_null': True},
        }

    def validate_ssc(self, value):
        return validate_percentage(value, "SSC marks")

    def validate_hsc(self, value):
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_diploma(self, value):
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_main_marks(self, value):
        return validate_percentage(value, "Main Marks")

    def validate_viva_marks(self, value):
        return validate_percentage(value, "Viva marks")

    def validate(self, data):
        faculty = data.get('faculty')
        if not faculty and not data.get('department'):
            raise serializers.ValidationError("Faculty must be specified.")
        if faculty:
            existing = MarksDistribution.objects.filter(faculty=faculty)
            if self.instance:
                existing = existing.exclude(id=self.instance.id)
            if existing.exists():
                raise serializers.ValidationError(f"Marks distribution for faculty '{faculty.faculty_name}' already exists.")
        return normalize_shared_academic_weight(self, data)


class MarksDistributionUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating MarksDistribution"""
    
    class Meta:
        model = MarksDistribution
        fields = ['faculty', 'department', 'ssc', 'hsc', 'diploma', 'main_marks', 'viva_marks']
        extra_kwargs = {
            'faculty': {'required': False, 'allow_null': True},
            'department': {'required': False, 'allow_null': True},
            'ssc': {'required': False},
            'hsc': {'required': False},
            'diploma': {'required': False},
            'main_marks': {'required': False},
            'viva_marks': {'required': False},
        }
        
    def validate_ssc(self, value):
        return validate_percentage(value, "SSC marks")

    def validate_hsc(self, value):
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_diploma(self, value):
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_main_marks(self, value):   
        return validate_percentage(value, "Main Marks")

    def validate_viva_marks(self, value):   
        return validate_percentage(value, "Viva marks")

    def validate(self, data):
        return normalize_shared_academic_weight(self, data)
