"""Serializers for reps and rep-customer assignments."""

from __future__ import annotations

from rest_framework import serializers

from apps.reps.models import Rep, RepCustomerAssignment


class RepAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for rep details with work days in customer assignment context."""
    
    rep_id = serializers.IntegerField(source='id', read_only=True)
    rep_name = serializers.CharField(source='name', read_only=True)
    rep_phone = serializers.CharField(source='phone', read_only=True)
    company_id = serializers.IntegerField(read_only=True)
    assignment_work_days = serializers.SerializerMethodField()
    
    class Meta:
        model = Rep
        fields = [
            'rep_id',
            'rep_name',
            'rep_phone',
            'company_id',
            'work_days',
            'assignment_work_days',
        ]
    
    def get_assignment_work_days(self, obj):
        """Get work days for this specific customer-rep assignment."""
        customer_id = self.context.get('customer_id')
        if not customer_id:
            return obj.work_days
        
        try:
            assignment = RepCustomerAssignment.objects.get(
                rep_id=obj.id,
                customer_id=customer_id
            )
            return assignment.work_days if assignment.work_days else obj.work_days
        except RepCustomerAssignment.DoesNotExist:
            return obj.work_days


class RepCustomerAssignmentSerializer(serializers.Serializer):
    """Serializer for assigning reps to customers with work days."""
    
    rep_id = serializers.IntegerField(required=True)
    work_days = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Work days for this assignment (e.g., ['sunday', 'monday']). Empty means use rep's default."
    )
    
    def validate_work_days(self, value):
        """Validate work days are valid day names."""
        valid_days = {
            'sunday', 'monday', 'tuesday', 'wednesday', 
            'thursday', 'friday', 'saturday',
            'الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء',
            'الخميس', 'الجمعة', 'السبت'
        }
        
        if value:
            invalid_days = [day for day in value if day.lower() not in valid_days]
            if invalid_days:
                raise serializers.ValidationError(
                    f"أيام غير صالحة: {', '.join(invalid_days)}"
                )
        
        return [day.lower() for day in value] if value else []


class CustomerLocationWorkDaysUpdateSerializer(serializers.Serializer):
    """Serializer for rep updating customer location and work days."""
    
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True
    )
    work_days = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Work days for this customer"
    )
    
    def validate_work_days(self, value):
        """Validate work days are valid day names."""
        valid_days = {
            'sunday', 'monday', 'tuesday', 'wednesday', 
            'thursday', 'friday', 'saturday',
            'الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء',
            'الخميس', 'الجمعة', 'السبت'
        }
        
        if value:
            invalid_days = [day for day in value if day.lower() not in valid_days]
            if invalid_days:
                raise serializers.ValidationError(
                    f"أيام غير صالحة: {', '.join(invalid_days)}"
                )
        
        return [day.lower() for day in value] if value else []
    
    def validate(self, data):
        """Validate GPS coordinates are provided together."""
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        # Both or neither (but allow null for both to clear location)
        if (latitude is not None) != (longitude is not None):
            raise serializers.ValidationError({
                "location": "يجب تقديم خطوط الطول والعرض معاً أو تركهما فارغين"
            })
        
        return data
