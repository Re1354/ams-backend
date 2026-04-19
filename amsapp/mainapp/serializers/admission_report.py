from rest_framework import serializers


class AnswerDisplaySerializer(serializers.Serializer):
    key = serializers.CharField(allow_null=True, required=False)
    text = serializers.CharField(allow_null=True, required=False)


class QuestionReviewSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    subject = serializers.CharField()
    question_text = serializers.CharField()
    question_type = serializers.CharField()
    marks = serializers.FloatField()
    options = serializers.DictField(required=False)
    student_answer = AnswerDisplaySerializer(allow_null=True)
    correct_answers = serializers.ListField(child=AnswerDisplaySerializer())
    status = serializers.ChoiceField(choices=["CORRECT", "WRONG", "SKIPPED"])
    is_correct = serializers.BooleanField()


class SubjectSummarySerializer(serializers.Serializer):
    sl = serializers.IntegerField()
    subject_name = serializers.CharField()
    total_questions = serializers.IntegerField()
    correct_answers = serializers.IntegerField()
    wrong_answers = serializers.IntegerField()
    skipped_answers = serializers.IntegerField()
    obtained_marks = serializers.FloatField()
    total_marks = serializers.FloatField()


class VivaRubricRowSerializer(serializers.Serializer):
    sl = serializers.IntegerField()
    source_rubric_id = serializers.IntegerField(allow_null=True, required=False)
    criteria = serializers.CharField()
    max_marks = serializers.FloatField()
    awarded_marks = serializers.FloatField()


class StudentAdmissionDetailReportSerializer(serializers.Serializer):
    student = serializers.DictField()
    written_exam = serializers.DictField()
    written_summary = serializers.DictField()
    subject_summary = serializers.ListField(child=SubjectSummarySerializer())
    question_reviews = serializers.ListField(child=QuestionReviewSerializer())
    viva = serializers.DictField()
    final_result = serializers.DictField()

