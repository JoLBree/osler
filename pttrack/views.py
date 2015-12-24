from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseRedirect, HttpResponseServerError, \
    HttpResponseNotFound
from django.views.generic.edit import FormView, UpdateView
from django.core.urlresolvers import reverse, reverse_lazy
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
import django.utils.timezone

from . import models as mymodels
from followup import models as fu_models
from . import forms as myforms

import datetime


def get_clindates():
    clindates = mymodels.ClinicDate.objects.filter(
        clinic_date=django.utils.timezone.now().date())
    return clindates


def get_current_provider_type(request):
    '''
    Given the request, produce the ProviderType of the logged in user. This is
    done using session data.
    '''
    return get_object_or_404(mymodels.ProviderType,
                             pk=request.session['clintype_pk'])


def get_cal():
    '''Get the gcal_id of the google calendar clinic date today.
    CURRENTLY BROKEN next_date must be produced correctly.'''
    import requests

    with open('google_secret.txt') as f:
        # TODO ip-restrict access to this key for halstead only
        GOOGLE_SECRET = f.read().strip()

    cal_url = "https://www.googleapis.com/calendar/v3/calendars/"
    calendar_id = "7eie7k06g255baksfshfhp0m28%40group.calendar.google.com"

    payload = {"key": GOOGLE_SECRET,
               "singleEvents": True,
               "timeMin":
               datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
               "orderBy": "startTime"}

    r = requests.get("".join([cal_url,
                              calendar_id,
                              '/events']),
                     params=payload)

    # draw the first starting time out of the JSON-formatted gcal api output
    javascript_datetime = r.json()["items"][0]["start"]["dateTime"]
    next_date = javascript_datetime.split("T")[0].split("-")

    next_date = datetime.datetime.date(year=next_date_str[0],
                                       month=next_date_str[1],
                                       day=next_date_str[2])

    return next_date


class NoteFormView(FormView):
    note_type = None

    def get_context_data(self, **kwargs):
        '''Inject self.note_type as the note type.'''

        if self.note_type is None:
            raise ImproperlyConfigured("NoteCreate view must have" +
                                       "'note_type' variable set.")

        context = super(FormView, self).get_context_data(**kwargs)
        context['note_type'] = self.note_type

        if 'pt_id' in self.kwargs:
            context['patient'] = mymodels.Patient.objects. \
                get(pk=self.kwargs['pt_id'])

        return context


class NoteUpdate(UpdateView):
    note_type = None

    def get_context_data(self, **kwargs):
        '''Inject self.note_type as the note type.'''

        if self.note_type is None:
            raise ImproperlyConfigured("NoteUpdate view must have" +
                                       "'note_type' variable set.")

        context = super(UpdateView, self).get_context_data(**kwargs)
        context['note_type'] = self.note_type

        return context

    # TODO: add shared form_valid code here from all subclasses.


class ProviderCreate(FormView):
    '''A view for creating a new Provider to match an existing User.'''
    template_name = 'pttrack/new-provider.html'
    form_class = myforms.ProviderForm

    def get_initial(self):

        return {'first_name': self.request.user.first_name,
                'last_name': self.request.user.last_name}

    def form_valid(self, form):
        provider = form.save(commit=False)
        provider.associated_user = self.request.user

        # populate the User object with the email and name data from the
        # Provider form
        user = provider.associated_user
        user.email = form.cleaned_data['provider_email']
        user.first_name = provider.first_name
        user.last_name = provider.last_name
        
        user.save()
        provider.save()
        form.save_m2m()

        return HttpResponseRedirect(self.request.GET['next'])

    def get_context_data(self, **kwargs):
        context = super(ProviderCreate, self).get_context_data(**kwargs)
        context['next'] = self.request.GET.get('next')
        return context


class ClinicDateCreate(FormView):
    '''A view for creating a new ClinicDate. On submission, it redirects to
    the new-workup view.'''
    template_name = 'pttrack/clindate.html'
    form_class = myforms.ClinicDateForm

    def form_valid(self, form):
        clindate = form.save(commit=False)

        today = datetime.datetime.date(django.utils.timezone.now())
        clindate.clinic_date = today
        clindate.save()

        # determine from our URL which patient we wanted to work up before we
        # got redirected to create a clinic date

        pt = get_object_or_404(mymodels.Patient, pk=self.kwargs['pt_id'])
        return HttpResponseRedirect(reverse("new-workup", args=(pt.id,)))


def followup_choice(request, pt_id):
    '''Prompt the user to choose a follow up type.'''
    pt = get_object_or_404(mymodels.Patient, pk=pt_id)
    return render(request, 'pttrack/followup-choice.html', {'patient': pt})


class WorkupCreate(NoteFormView):
    '''A view for creating a new workup. Checks to see if today is a
    clinic date first, and prompts its creation if none exist.'''
    template_name = 'pttrack/form_submission.html'
    form_class = myforms.WorkupForm
    note_type = 'Workup'

    def get(self, *args, **kwargs):
        """Check that we have an instantiated ClinicDate today,
        then dispatch to get() of the superclass view."""

        clindates = get_clindates()
        pt = get_object_or_404(mymodels.Patient, pk=kwargs['pt_id'])

        if len(clindates) == 0:
            # dispatch to ClinicDateCreate because the ClinicDate doesn't exist
            return HttpResponseRedirect(reverse("new-clindate", args=(pt.id,)))
        elif len(clindates) == 1:
            # dispatch to our own view, since we know there's a ClinicDate
            # for today
            kwargs['pt_id'] = pt.id
            return super(WorkupCreate,
                         self).get(self, *args, **kwargs)
        else:  # we have >1 clindate today.
            return HttpResponseServerError("<h3>We don't know how to handle " +
                                           ">1 clinic day on a particular " +
                                           "day!</h3>")

    def form_valid(self, form):
        pt = get_object_or_404(mymodels.Patient, pk=self.kwargs['pt_id'])
        active_provider_type = get_object_or_404(mymodels.ProviderType,
                                             pk=self.request.session['clintype_pk'])
        wu = form.save(commit=False)
        wu.patient = pt
        wu.author = self.request.user.provider
        wu.author_type = get_current_provider_type(self.request)
        wu.clinic_day = get_clindates()[0]
        if wu.author_type.signs_charts:
            wu.sign(self.request.user, active_provider_type)

        wu.save()

        form.save_m2m()

        return HttpResponseRedirect(reverse("new-action-item", args=(pt.id,)))


class WorkupUpdate(NoteUpdate):
    template_name = "pttrack/form-update.html"
    model = mymodels.Workup
    form_class = myforms.WorkupForm
    note_type = "Workup"

    def form_valid(self, form):
        wu = form.save(commit=False)
        current_user_type = get_current_provider_type(self.request)
        if wu.signer is None:
            wu.save()
            form.save_m2m()
            return HttpResponseRedirect(reverse("workup", args=(wu.id,)))
        else:
            if current_user_type.signs_charts:
                wu.save()
                form.save_m2m()
                return HttpResponseRedirect(reverse("workup", args=(wu.id,)))
            else:
                return HttpResponseRedirect(reverse("workup-error",
                                                    args=(wu.id,)))

class ActionItemCreate(NoteFormView):
    '''A view for creating ActionItems using the ActionItemForm.'''
    template_name = 'pttrack/form_submission.html'
    form_class = myforms.ActionItemForm
    note_type = 'Action Item'

    def form_valid(self, form):
        '''Set the patient, provider, and written timestamp for the item.'''
        pt = get_object_or_404(mymodels.Patient, pk=self.kwargs['pt_id'])
        ai = form.save(commit=False)

        ai.completion_date = None
        ai.author = self.request.user.provider
        ai.author_type = get_current_provider_type(self.request)
        ai.patient = pt

        ai.save()

        return HttpResponseRedirect(reverse("patient-detail", args=(pt.id,)))


class PatientUpdate(UpdateView):
    template_name = 'pttrack/patient-update.html'
    model = mymodels.Patient
    form_class = myforms.PatientForm

    def get_success_url(self):
        pt = self.object
        return reverse("patient-detail", args=(pt.id, ))


class PatientCreate(FormView):
    '''A view for creating a new patient using PatientForm.'''
    template_name = 'pttrack/intake.html'
    form_class = myforms.PatientForm

    def form_valid(self, form):
        pt = form.save()

        # Action of creating the patient should indicate the patient is active (needs a workup)
        pt.needs_workup = True

        if not '-' in pt.ssn:
            pt.ssn = pt.ssn[0:3] + '-' + pt.ssn[3:5] + '-' + pt.ssn[5:]

        pt.save()
        return HttpResponseRedirect(reverse("patient-detail",
                                            args=(pt.id,)))


class DocumentUpdate(NoteUpdate):
    template_name = "pttrack/form-update.html"
    model = mymodels.Document
    form_class = myforms.DocumentForm
    note_type = "Document"

    def get_success_url(self):
        doc = self.object
        return reverse("document-detail", args=(doc.id, ))


class DocumentCreate(NoteFormView):
    '''A view for uploading a document'''
    template_name = 'pttrack/form_submission.html'
    form_class = myforms.DocumentForm
    note_type = 'Document'

    def form_valid(self, form):
        doc = form.save(commit=False)

        pt = get_object_or_404(mymodels.Patient, pk=self.kwargs['pt_id'])
        doc.patient = pt
        doc.author = self.request.user.provider
        doc.author_type = get_current_provider_type(self.request)

        doc.save()

        return HttpResponseRedirect(reverse("patient-detail", args=(pt.id,)))


def choose_clintype(request):
    RADIO_CHOICE_KEY = 'radio-roles'

    if request.POST:
        request.session['clintype_pk'] = request.POST[RADIO_CHOICE_KEY]
        return HttpResponseRedirect(request.GET['next'])

    if request.GET:
        role_options = request.user.provider.clinical_roles.all()

        if len(role_options) == 1:
            request.session['clintype_pk'] = role_options[0].pk
            return HttpResponseRedirect(request.GET['next'])
        elif len(role_options) == 0:
            return HttpResponseServerError(
                "Fatal: your Provider register is corrupted, and lacks " +
                "ProviderTypes. Report this error!")
        else:
            return render(request, 'pttrack/role-choice.html',
                          {'roles': role_options,
                           'choice_key': RADIO_CHOICE_KEY})


def home_page(request):
    active_provider_type = get_object_or_404(mymodels.ProviderType,
                                             pk=request.session['clintype_pk'])
    if active_provider_type.signs_charts:
        workup_list = mymodels.Workup.objects.all()
        pt_list_1 = list(set([wu.patient for wu in workup_list if wu.signer is None]))
        patient_list = mymodels.Patient.objects.all().order_by('last_name')
        pt_list_2 = []

        for patient in patient_list:
            if (patient.needs_workup):
                pt_list_2.append(patient)
        
        def byName_key(patient):
            return patient.last_name

        pt_list_1.sort(key = byName_key)
        pt_list_2.sort(key = byName_key)
        title = "Attending Tasks"
        pt_list_list = [pt_list_1, pt_list_2]
        sectiontitle_list = ["Patients with Unsigned Workups", "Active Patients"]
        zipped_list = zip(sectiontitle_list,pt_list_list)


        return render(request,
                  'pttrack/patient_list.html',
                  {'zipped_list': zipped_list,
                    'title': title})

    elif active_provider_type.short_name == "Coordinator":
        ai_list = mymodels.ActionItem.objects.filter(
            due_date__lte=django.utils.timezone.now().today())

        ai_list_2 = mymodels.ActionItem.objects.filter(
            due_date__gt=django.utils.timezone.now().today()).order_by('due_date')


        patient_list = mymodels.Patient.objects.all().order_by('last_name')
        pt_list_1 = []

        def byName_key(patient):
            return patient.last_name

        pt_list_1.sort(key = byName_key)

        for patient in patient_list:
            if (patient.needs_workup):
                pt_list_1.append(patient)

        # if the AI is marked as done, it doesn't contribute to the pt being on
        # the list.
        pt_list_2 = list(set([ai.patient for ai in ai_list if not ai.done()]))

        # The third list consists of patients that have action items due
        pt_list_3 = list(set([ai.patient for ai in ai_list_2 if not ai.done()]))

        def byAI_key(patient):
            return patient.inactive_action_items()[0].due_date

        pt_list_3.sort(key = byAI_key)


        title = "Coordinator Tasks"
        pt_list_list = [pt_list_1, pt_list_2, pt_list_3]
        sectiontitle_list = ["Active Patients", "Active Action Items", "Pending Action Items"]
        zipped_list = zip(sectiontitle_list,pt_list_list)


        return render(request,
                  'pttrack/patient_list.html',
                  {'zipped_list': zipped_list,
                    'title': title})

    else:
        patient_list = mymodels.Patient.objects.all().order_by('last_name')
        pt_list = []

        def byName_key(patient):
            return patient.last_name

        pt_list.sort(key = byName_key)

        for patient in patient_list:
            if (patient.needs_workup):
                pt_list.append(patient)

        title = "Active Patients"
        pt_list_list = [pt_list]
        sectiontitle_list = ["Active Patients"]
        zipped_list = zip(sectiontitle_list,pt_list_list)


        return render(request,
                  'pttrack/patient_list.html',
                  {'zipped_list': zipped_list,
                    'title': title})


def phone_directory(request):
    patient_list = mymodels.Patient.objects.all().order_by('last_name')

    title = "Patient Phone Number Directory"
    return render(request,
                  'pttrack/phone_directory.html',
                  {'object_list': patient_list,
                    'title': title})
    

def error_workup(request, pk):

    wu = get_object_or_404(mymodels.Workup, pk=pk)
    return render(request,
                  'pttrack/workup_error.html',
                  {'workup': wu})

def all_patients(request):
    pt_list = list(mymodels.Patient.objects.all().order_by('last_name'))
    pt_list_list = [pt_list]
    sectiontitle_list = ["Alphabetized by Last Name"]
    zipped_list = zip(sectiontitle_list,pt_list_list)
    return render(request,
                  'pttrack/patient_list.html',
                  {'zipped_list': zipped_list,
                    'title': "All Patients"})


def sign_workup(request, pk):
    wu = get_object_or_404(mymodels.Workup, pk=pk)
    active_provider_type = get_object_or_404(mymodels.ProviderType,
                                             pk=request.session['clintype_pk'])

    pt = wu.patient
    wu.sign(request.user, active_provider_type)


    wu.save()

    return HttpResponseRedirect(reverse("workup", args=(wu.id,)))

def patient_activate_detail(request, pk):
    pt = get_object_or_404(mymodels.Patient, pk=pk)

    pt.change_active_status()

    pt.save()

    return HttpResponseRedirect(reverse("patient-detail", args=(pt.id,)))

def patient_activate_home(request, pk):
    pt = get_object_or_404(mymodels.Patient, pk=pk)

    pt.change_active_status()

    pt.save()

    return HttpResponseRedirect(reverse("home"))

def done_action_item(request, ai_id):
    ai = get_object_or_404(mymodels.ActionItem, pk=ai_id)
    ai.mark_done(request.user.provider)
    ai.save()

    return HttpResponseRedirect(reverse("followup-choice",
                                        args=(ai.patient.pk,)))


def reset_action_item(request, ai_id):
    ai = get_object_or_404(mymodels.ActionItem, pk=ai_id)
    ai.clear_done()
    ai.save()
    return HttpResponseRedirect(reverse("patient-detail",
                                        args=(ai.patient.id,)))

class UserCreate(FormView):
    template_name = 'pttrack/new-user.html'
    form_class = UserCreationForm

    def form_valid(self, form):
        user = form.save()

        return reverse("home")
