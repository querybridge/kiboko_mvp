from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from users.forms import UserRegistrationForm

# Create your views here.
@login_required
#Logout View
def logout_view(request):
	logout(request)
	return HttpResponseRedirect(reverse('app:index'))


#Registration Page
def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Set the role on the auto-created profile
            user.profile.role = form.cleaned_data['role']
            user.profile.save()
            username = form.cleaned_data.get('username')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=raw_password)
            login(request, user)
            return redirect('app:analytics_grow_sales')
    else:
        form = UserRegistrationForm()
    return render(request, 'users/register.html', {'form': form})
