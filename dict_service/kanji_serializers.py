from rest_framework import serializers


class KanjiRecognizeRequestSerializer(serializers.Serializer):
    strokes = serializers.ListField(child=serializers.ListField(child=serializers.ListField(child=serializers.FloatField())))
    top_n = serializers.IntegerField(required=False, min_value=1, max_value=20, default=5)

    def validate_strokes(self, value):
        if not isinstance(value, list) or len(value) == 0:
            raise serializers.ValidationError('strokes must be a non-empty list')
        for stroke in value:
            if not isinstance(stroke, list) or len(stroke) == 0:
                raise serializers.ValidationError('each stroke must be a non-empty list of points')
            for p in stroke:
                if not isinstance(p, list) or len(p) != 2:
                    raise serializers.ValidationError('each point must be [x, y]')
        return value


class KanjiRecognizeResultSerializer(serializers.Serializer):
    character = serializers.CharField()
    distance = serializers.FloatField()
    confidence = serializers.FloatField()


class KanjiRecognizeResponseSerializer(serializers.Serializer):
    results = KanjiRecognizeResultSerializer(many=True)
