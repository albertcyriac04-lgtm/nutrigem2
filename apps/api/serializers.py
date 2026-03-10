from rest_framework import serializers
from .models import UserProfile, FoodItem, ConsumptionLog, WeightRecord


class FoodItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodItem
        fields = ['id', 'name', 'calories', 'protein', 'carbs', 'fats', 'category', 'created_at', 'updated_at']


class WeightRecordSerializer(serializers.ModelSerializer):
    user_profile_id = serializers.IntegerField(write_only=True, required=False)
    
    class Meta:
        model = WeightRecord
        fields = ['id', 'date', 'weight', 'user_profile_id', 'created_at']
    
    def create(self, validated_data):
        # Get user_profile from context (nested route) or from validated_data (direct route)
        user_profile = self.context.get('user_profile')
        if not user_profile:
            user_profile_id = validated_data.pop('user_profile_id', None)
            if not user_profile_id:
                raise serializers.ValidationError({'user_profile_id': 'This field is required.'})
            try:
                user_profile = UserProfile.objects.get(id=user_profile_id)
            except UserProfile.DoesNotExist:
                raise serializers.ValidationError({'user_profile_id': 'User profile not found.'})
        
        validated_data['user_profile'] = user_profile
        return super().create(validated_data)


class ConsumptionLogSerializer(serializers.ModelSerializer):
    food_item = FoodItemSerializer(read_only=True)
    food_item_id = serializers.IntegerField(write_only=True)
    user_profile_id = serializers.IntegerField(write_only=True, required=False)
    total_calories = serializers.ReadOnlyField()
    
    class Meta:
        model = ConsumptionLog
        fields = ['id', 'date', 'meal_type', 'food_item', 'food_item_id', 'user_profile_id', 'quantity', 'total_calories', 'created_at']
    
    def create(self, validated_data):
        # Get user_profile from context (nested route) or from validated_data (direct route)
        user_profile = self.context.get('user_profile')
        if not user_profile:
            user_profile_id = validated_data.pop('user_profile_id', None)
            if not user_profile_id:
                raise serializers.ValidationError({'user_profile_id': 'This field is required.'})
            try:
                user_profile = UserProfile.objects.get(id=user_profile_id)
            except UserProfile.DoesNotExist:
                raise serializers.ValidationError({'user_profile_id': 'User profile not found.'})
        
        # Get food_item with error handling
        food_item_id = validated_data.pop('food_item_id')
        try:
            food_item = FoodItem.objects.get(id=food_item_id)
        except FoodItem.DoesNotExist:
            raise serializers.ValidationError({'food_item_id': 'Food item not found.'})
        
        validated_data['user_profile'] = user_profile
        validated_data['food_item'] = food_item
        return super().create(validated_data)


class UserProfileSerializer(serializers.ModelSerializer):
    consumption_logs = ConsumptionLogSerializer(many=True, read_only=True)
    weight_records = WeightRecordSerializer(many=True, read_only=True)
    food_allergies = serializers.CharField(required=False, allow_blank=True)
    medical_conditions = serializers.CharField(required=False, allow_blank=True)
    diet_restrictions = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'name', 'age', 'gender', 'height', 'weight', 
            'target_weight', 'activity_multiplier', 
            'food_allergies', 'medical_conditions', 'diet_restrictions', 'profile_image_url',
            'subscription_status', 'subscription_expires',
            'consumption_logs', 'weight_records',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        relation_fields = {
            'food_allergies': validated_data.pop('food_allergies', ''),
            'medical_conditions': validated_data.pop('medical_conditions', ''),
            'diet_restrictions': validated_data.pop('diet_restrictions', ''),
        }
        instance = super().create(validated_data)
        for field_name, value in relation_fields.items():
            setattr(instance, field_name, value)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        relation_fields = {}
        for field_name in ('food_allergies', 'medical_conditions', 'diet_restrictions'):
            if field_name in validated_data:
                relation_fields[field_name] = validated_data.pop(field_name)
        instance = super().update(instance, validated_data)
        for field_name, value in relation_fields.items():
            setattr(instance, field_name, value)
        if relation_fields:
            instance.save()
        return instance


class UserProfileListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list views"""
    food_allergies = serializers.CharField(read_only=True)
    medical_conditions = serializers.CharField(read_only=True)
    diet_restrictions = serializers.CharField(read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'id', 'name', 'age', 'gender', 'height', 'weight', 
            'target_weight', 'activity_multiplier', 
            'food_allergies', 'medical_conditions', 'diet_restrictions', 'profile_image_url',
            'subscription_status',
            'created_at', 'updated_at'
        ]

