"""Shared list edits never post money; a trip has one permanent expense."""
from django.db import models
from .models import FamilyRow


class ShoppingList(FamilyRow):
    name = models.CharField(max_length=120)
    archived = models.BooleanField(default=False)


class ShoppingItem(FamilyRow):
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.PROTECT, related_name='items')
    name = models.CharField(max_length=120)
    quantity = models.CharField(max_length=40, default='1')
    price_ore = models.PositiveBigIntegerField(null=True, blank=True)
    category = models.ForeignKey('budget.Category', null=True, blank=True, on_delete=models.PROTECT)
    purchased = models.BooleanField(default=False)
    removed = models.BooleanField(default=False)
    trip = models.ForeignKey('budget.ShoppingTrip', null=True, blank=True, on_delete=models.PROTECT, related_name='items')


class ShoppingTrip(FamilyRow):
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.PROTECT, related_name='trips')
    store = models.CharField(max_length=120)
    entry = models.OneToOneField('budget.Entry', on_delete=models.PROTECT, related_name='shopping_trip')
    receipt = models.ForeignKey('budget.Document', null=True, blank=True, on_delete=models.PROTECT, related_name='trips')
