from rest_framework import serializers
from ..models import MarksDistribution, Department


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
    
    class Meta:
        model = MarksDistribution
        fields = [
            'id', 'department', 'department_name', 'department_shortname', 
            'ssc', 'hsc', 'diploma', 'main_marks', 'viva_marks'
        ]
        read_only_fields = ['id']

    def validate_ssc(self, value):
        """Validate that SSC percentage is within range"""
        return validate_percentage(value, "SSC marks")

    def validate_hsc(self, value):
        """Validate that HSC/Diploma percentage is within range"""
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_diploma(self, value):
        """Validate that HSC/Diploma percentage is within range"""
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_main_marks(self, value):
        """Validate that Main Marks percentage is within range"""
        return validate_percentage(value, "Main Marks")

    def validate_viva_marks(self, value):
        """Validate that Viva marks percentage is within range"""
        return validate_percentage(value, "Viva marks")
    
    def validate_department(self, value):
        """Validate that the department exists"""
        if not Department.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Department does not exist")
        return value


class MarksDistributionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating MarksDistribution"""
    
    class Meta:
        model = MarksDistribution
        fields = ['department', 'ssc', 'hsc', 'diploma', 'main_marks', 'viva_marks']

    def validate_ssc(self, value):
        """Validate that SSC percentage is within range"""
        return validate_percentage(value, "SSC marks")

    def validate_hsc(self, value):
        """Validate that HSC/Diploma percentage is within range"""
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_diploma(self, value):
        """Validate that HSC/Diploma percentage is within range"""
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_main_marks(self, value):
        """Validate that Main Marks percentage is within range"""
        return validate_percentage(value, "Main Marks")

    def validate_viva_marks(self, value):
        """Validate that Viva marks percentage is within range"""
        return validate_percentage(value, "Viva marks")

    def validate(self, data):
        """Normalize HSC and Diploma to one shared academic weight"""
        return normalize_shared_academic_weight(self, data)


class MarksDistributionUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating MarksDistribution"""
    
    class Meta:
        model = MarksDistribution
        fields = ['ssc', 'hsc', 'diploma', 'main_marks', 'viva_marks']
        
    def validate_ssc(self, value):
        """Validate that SSC percentage is within range"""
        return validate_percentage(value, "SSC marks")

    def validate_hsc(self, value):
        """Validate that HSC/Diploma percentage is within range"""
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_diploma(self, value):
        """Validate that HSC/Diploma percentage is within range"""
        return validate_percentage(value, "HSC/Diploma marks")

    def validate_main_marks(self, value):   
        """Validate that Main Marks percentage is within range"""
        return validate_percentage(value, "Main Marks")

    def validate_viva_marks(self, value):   
        """Validate that Viva marks percentage is within range"""
        return validate_percentage(value, "Viva marks")

    def validate(self, data):
        """Normalize HSC and Diploma to one shared academic weight"""
        return normalize_shared_academic_weight(self, data)
