'''Forms for the SNHC clintools app.'''
from bootstrap3_datetime.widgets import DateTimePicker
from django.forms import ModelForm, ValidationError, Form
from django.forms import ModelChoiceField

from . import models
from . import followup_models

# pylint: disable=I0011,E1305


class GeneralFollowup(ModelForm):
    '''The form instantiation of a general followup note.'''
    class Meta:
        model = followup_models.GeneralFollowup
        exclude = ['patient', 'author', 'author_type']


class ReferralFollowup(ModelForm):
    '''The form instantiation of a followup for PCP referral.'''
    class Meta:
        model = followup_models.ReferralFollowup
        exclude = ['patient', 'author', 'author_type']

    def clean(self):
        '''ReferralFollowup has some pretty complicated behavior regarding
        which combinations of blank and filled fields are acceptable. We
        implement checks for this here.'''
        cleaned_data = super(ModelForm, self).clean()

        has_appointment = cleaned_data.get("has_appointment")

        if has_appointment:
            # If the patient has an appointment, we require a location and
            # information as to whether or not they showed up.

            if not cleaned_data.get("apt_location"):
                self.add_error("apt_location", "Appointment location is" +
                               "required when the patient has an appointment.")

            if not cleaned_data.get("pt_showed"):
                self.add_error("pt_showed", "Please specify whether the" +
                               "patient has gone to their appointment.")

            pt_went = cleaned_data.get("pt_showed")
            if pt_went == "No" and not cleaned_data.get("noshow_reason"):
                self.add_error("noshow_reason", "Why didn't the patient go" +
                               "to the appointment?")

        else:  # not has_appointment
            if not cleaned_data.get("noapt_reason"):
                self.add_error("noapt_reason", "Why didn't the patient make" +
                               "an appointment?")


class VaccineFollowup(ModelForm):
    '''A form to process the handling of a vaccine followup.'''
    class Meta:
        model = followup_models.VaccineFollowup
        exclude = ['patient', 'author', 'author_type']

    def clean(self):
        '''VaccineFollowups require a next dose date iff there there is a next
        dose.'''

        cleaned_data = super(ModelForm, self).clean()

        if cleaned_data.get('subsq_dose') and \
           not cleaned_data.get('dose_date'):

            self.add_error('dose_date', 'A next dosage date is required if ' +
                           'the patient is returning for another dose.')


class LabFollowup(ModelForm):
    '''The form instantiation of a followup to communicate lab results.'''
    class Meta:
        model = followup_models.LabFollowup
        exclude = ['patient', 'author', 'author_type']


class PatientForm(ModelForm):
    class Meta:
        model = models.Patient
        exclude = []


class WorkupForm(ModelForm):
    class Meta:
        model = models.Workup
        exclude = ['patient', 'clinic_day', 'author', 'signer', 'author_type',
                   'signed_date']

    def clean(self):
        '''Use form's clean hook to verify that fields in Workup are
        consistent with one another (e.g. if pt recieved a voucher, amount is
        given).'''

        cleaned_data = super(ModelForm, self).clean()

        if cleaned_data.get('got_voucher') and \
           not cleaned_data.get('voucher_amount'):

            self.add_error('voucher_amount', "If the patient recieved a " +
                           "voucher, value of the voucher must be specified.")

        if cleaned_data.get('got_voucher') and \
           not cleaned_data.get('patient_pays'):

            self.add_error('patient_pays', "If the patient recieved a " +
                           "voucher, specify the amount the patient pays.")


class ActionItemForm(ModelForm):
    class Meta:
        model = models.ActionItem
        exclude = ['completion_date', 'author', 'written_date', 'patient',
                   'completion_author', 'author_type']
        widgets = {'due_date': DateTimePicker(options={"format": "YYYY-MM-DD",
                                                       "pickTime": False})}


class ProviderForm(ModelForm):
    class Meta:
        model = models.Provider
        exclude = ['associated_user']


class ClinicDateForm(ModelForm):
    class Meta:
        model = models.ClinicDate
        exclude = ['clinic_date', 'gcal_id']
