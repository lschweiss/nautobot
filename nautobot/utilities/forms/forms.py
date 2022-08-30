import json
import re

import yaml
from django import forms
from django.forms import formset_factory, BaseFormSet

from nautobot.ipam.formfields import IPNetworkFormField
from nautobot.utilities.utils import get_filterset_for_model, build_lookup_label, get_filterset_field_data

__all__ = (
    "AddressFieldMixin",
    "BootstrapMixin",
    "BulkEditForm",
    "BulkRenameForm",
    "ConfirmationForm",
    "CSVModelForm",
    "DynamicFilterForm",
    "ImportForm",
    "PrefixFieldMixin",
    "ReturnURLForm",
    "TableConfigForm",
)


class AddressFieldMixin(forms.ModelForm):
    """
    ModelForm mixin for IPAddress based models.
    """

    address = IPNetworkFormField()

    def __init__(self, *args, **kwargs):

        instance = kwargs.get("instance")
        initial = kwargs.get("initial", {}).copy()

        # If initial already has an `address`, we want to use that `address` as it was passed into
        # the form. If we're editing an object with a `address` field, we need to patch initial
        # to include `address` because it is a computed field.
        if "address" not in initial and instance is not None:
            initial["address"] = instance.address

        kwargs["initial"] = initial

        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()

        # Need to set instance attribute for `address` to run proper validation on Model.clean()
        self.instance.address = self.cleaned_data.get("address")


class BootstrapMixin(forms.BaseForm):
    """
    Add the base Bootstrap CSS classes to form elements.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        exempt_widgets = [
            forms.CheckboxInput,
            forms.ClearableFileInput,
            forms.FileInput,
            forms.RadioSelect,
        ]

        for field_name, field in self.fields.items():
            if field.widget.__class__ not in exempt_widgets:
                css = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = " ".join([css, "form-control"]).strip()
            if field.required and not isinstance(field.widget, forms.FileInput):
                field.widget.attrs["required"] = "required"
            if "placeholder" not in field.widget.attrs:
                field.widget.attrs["placeholder"] = field.label


class ReturnURLForm(forms.Form):
    """
    Provides a hidden return URL field to control where the user is directed after the form is submitted.
    """

    return_url = forms.CharField(required=False, widget=forms.HiddenInput())


class ConfirmationForm(BootstrapMixin, ReturnURLForm):
    """
    A generic confirmation form. The form is not valid unless the confirm field is checked.
    """

    confirm = forms.BooleanField(required=True, widget=forms.HiddenInput(), initial=True)


class BulkEditForm(forms.Form):
    """
    Base form for editing multiple objects in bulk.

    Note that for models supporting custom fields and relationships, nautobot.extras.forms.NautobotBulkEditForm is
    a more powerful subclass and should be used instead of directly inheriting from this class.
    """

    def __init__(self, model, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model
        self.nullable_fields = []

        # Copy any nullable fields defined in Meta
        if hasattr(self.Meta, "nullable_fields"):
            self.nullable_fields = self.Meta.nullable_fields


class BulkRenameForm(forms.Form):
    """
    An extendable form to be used for renaming objects in bulk.
    """

    find = forms.CharField()
    replace = forms.CharField()
    use_regex = forms.BooleanField(required=False, initial=True, label="Use regular expressions")

    def clean(self):
        super().clean()

        # Validate regular expression in "find" field
        if self.cleaned_data["use_regex"]:
            try:
                re.compile(self.cleaned_data["find"])
            except re.error:
                raise forms.ValidationError({"find": "Invalid regular expression"})


class CSVModelForm(forms.ModelForm):
    """
    ModelForm used for the import of objects in CSV format.
    """

    def __init__(self, *args, headers=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Modify the model form to accommodate any customized to_field_name properties
        if headers:
            for field, to_field in headers.items():
                if to_field is not None:
                    self.fields[field].to_field_name = to_field


class PrefixFieldMixin(forms.ModelForm):
    """
    ModelForm mixin for IPNetwork based models.
    """

    prefix = IPNetworkFormField()

    def __init__(self, *args, **kwargs):

        instance = kwargs.get("instance")
        initial = kwargs.get("initial", {}).copy()

        # If initial already has a `prefix`, we want to use that `prefix` as it was passed into
        # the form. If we're editing an object with a `prefix` field, we need to patch initial
        # to include `prefix` because it is a computed field.
        if "prefix" not in initial and instance is not None:
            initial["prefix"] = instance.prefix

        kwargs["initial"] = initial

        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()

        # Need to set instance attribute for `prefix` to run proper validation on Model.clean()
        self.instance.prefix = self.cleaned_data.get("prefix")


class ImportForm(BootstrapMixin, forms.Form):
    """
    Generic form for creating an object from JSON/YAML data
    """

    data = forms.CharField(
        widget=forms.Textarea,
        help_text="Enter object data in JSON or YAML format. Note: Only a single object/document is supported.",
        label="",
    )
    format = forms.ChoiceField(choices=(("json", "JSON"), ("yaml", "YAML")), initial="yaml")

    def clean(self):
        super().clean()

        data = self.cleaned_data["data"]
        format = self.cleaned_data["format"]

        # Process JSON/YAML data
        if format == "json":
            try:
                self.cleaned_data["data"] = json.loads(data)
                # Check for multiple JSON objects
                if not isinstance(self.cleaned_data["data"], dict):
                    raise forms.ValidationError({"data": "Import is limited to one object at a time."})
            except json.decoder.JSONDecodeError as err:
                raise forms.ValidationError({"data": "Invalid JSON data: {}".format(err)})
        else:
            # Check for multiple YAML documents
            if "\n---" in data:
                raise forms.ValidationError({"data": "Import is limited to one object at a time."})
            try:
                self.cleaned_data["data"] = yaml.load(data, Loader=yaml.SafeLoader)
            except yaml.error.YAMLError as err:
                raise forms.ValidationError({"data": "Invalid YAML data: {}".format(err)})


class TableConfigForm(BootstrapMixin, forms.Form):
    """
    Form for configuring user's table preferences.
    """

    columns = forms.MultipleChoiceField(
        choices=[],
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 10}),
        help_text="Use the buttons below to arrange columns in the desired order, then select all columns to display.",
    )

    def __init__(self, table, *args, **kwargs):
        self.table = table

        super().__init__(*args, **kwargs)

        # Initialize columns field based on table attributes
        self.fields["columns"].choices = table.configurable_columns
        self.fields["columns"].initial = table.visible_columns

    @property
    def table_name(self):
        return self.table.__class__.__name__


class DynamicFilterForm(BootstrapMixin, forms.Form):
    """
    Form for configuring user's filter form preferences.
    """

    lookup_field = forms.ChoiceField(
        choices=[],
        required=False,
        label="Field",
    )
    lookup_type = forms.ChoiceField(
        choices=[],
        required=False,
    )
    value = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        contenttype = self.model._meta.app_label + "." + self.model._meta.model_name

        # Configure fields: Add css class and set choices for lookup_field
        self.fields["lookup_field"].choices = [(None, None)] + self.get_lookup_expr_choices()
        self.fields["lookup_field"].widget.attrs["class"] = "nautobot-select2-static lookup_field-select"

        # Populate lookup type if item present in data
        data = kwargs.get("data")
        prefix = kwargs.get("prefix")
        if data and prefix:
            lookup_type = data.getlist(prefix + "-lookup_type")
            lookup_value = data.getlist(prefix + "-value")
            if lookup_type:
                label = build_lookup_label(lookup_type[0])
                self.fields["lookup_type"].choices = [(lookup_type[0], label)]

            if lookup_type and lookup_value:
                self.select_or_input_data(lookup_type[0], lookup_value)

        # data-query-param-group_id="["$tenant_group"]"
        self.fields["lookup_type"].widget.attrs["data-query-param-field_name"] = json.dumps(["$lookup_field"])
        self.fields["lookup_type"].widget.attrs["data-contenttype"] = contenttype
        self.fields["lookup_type"].widget.attrs["data-url"] = "/lookup-choices/"
        self.fields["lookup_type"].widget.attrs["class"] = "nautobot-select2-api lookup_type-select"

        lookup_value_css = self.fields["value"].widget.attrs.get("class")
        self.fields["value"].widget.attrs["class"] = " ".join([lookup_value_css, "value-input form-control"])

    def select_or_input_data(self, field_name, choice):
        from nautobot.utilities.forms import StaticSelect2
        from nautobot.utilities.forms import APISelect, APISelectMultiple

        # Static choice and Dynamic Choice and Yes/No Choice
        data = get_filterset_field_data(self.model, field_name, choice)
        if data["type"] == "static-choices":
            allow_multiple = data["allow_multiple"]
            attr = {}
            if allow_multiple:
                attr["multiple"] = "true"

            self.fields["value"] = forms.ChoiceField(
                choices=data["choices"],
                required=False,
                widget=StaticSelect2(attrs={**attr}),
                initial=choice
            )
        elif data["type"] == "dynamic-choices":
            # Add contenttype if needed like status and tags

            api_attr = {}
            if data.get("content_type") is not None:
                api_attr["data-query-param-content_types"] = data["content_type"]
            if data.get("value_field") is not None:
                api_attr["value-field"] = data["value_field"]

            self.fields["value"] = forms.ChoiceField(
                choices=data["choices"],
                required=False,
                widget=APISelectMultiple(api_url=data["data_url"], attrs={**api_attr}),
                initial=choice
            )

    @staticmethod
    def capitalize(field):
        data = field.split("_")
        first_word = data[0][0].upper() + data[0][1:]
        return " ".join([first_word, *data[1:]])

    def get_lookup_expr_choices(self):
        filterset = get_filterset_for_model(self.model).base_filters
        filterset_without_lookup = []

        for name, field in filterset.items():
            if "__" not in name:
                filterset_without_lookup.append((name, field.label or self.capitalize(field.field_name)))

        return filterset_without_lookup


class DynamicFilterFormBaseFormSet(BaseFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __iter__(self):
        """Yield the forms in the order they should be rendered."""
        return iter(self.forms)

    def _construct_form(self, i, **kwargs):
        # form = super()._construct_form(i, **kwargs)
        """Instantiate and return the i-th form instance in a formset."""
        defaults = {
            'auto_id': self.auto_id,
            'prefix': self.add_prefix(i),
            'error_class': self.error_class,
            # Don't render the HTML 'required' attribute as it may cause
            # incorrect validation for extra, optional, and deleted
            # forms in the formset.
            'use_required_attribute': False,
        }
        if self.is_bound:
            defaults['data'] = self.data
            defaults['files'] = self.files
        if self.initial and 'initial' not in kwargs:
            try:
                defaults['initial'] = self.initial[i]
            except IndexError:
                pass
        # Allow extra forms to be empty, unless they're part of
        # the minimum forms.
        if i >= self.initial_form_count() and i >= self.min_num:
            defaults['empty_permitted'] = True
        defaults.update(kwargs)
        form = self.form(**defaults)
        self.add_fields(form, i)
        return form


def dynamic_formset_factory(model, data=None, **kwargs):
    modelform = DynamicFilterForm
    modelform.model = model

    params = {
        "can_delete_extra": True,
        "can_delete": True,
        "extra": 3,
    }

    kwargs.update(params)
    form = formset_factory(form=DynamicFilterForm, formset=DynamicFilterFormBaseFormSet, **kwargs)
    if data:
        form = form(data=data)

    return form


DynamicFilterFormSet = dynamic_formset_factory


