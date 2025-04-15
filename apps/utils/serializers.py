from rest_framework import serializers

class AbstractBaseSerializer(serializers.ModelSerializer):
    uid = serializers.UUIDField(required=False)
    slug = serializers.SlugField(required=False)
    updated_at = serializers.DateTimeField(required=False)
    created_at = serializers.DateTimeField(required=False)

    class Meta:
        abstract = True
        fields = ["uid", "slug", "created_at", "updated_at"]
        read_only_fields = ("uid", "slug", "created_at", "updated_at")