from django.conf import settings
from django.http import HttpResponseRedirect

# LoginRequiredMixin
# This mixin allows our views to be auth controlled and we
# can change the settings from the urls.py level.
#
# A url might look like: 
# url(r'^backoffice/members/$', <View>.as_view(template_name = ..., login_required = True, login_redirect_location = '/backoffice/login/'))
#
# You can also set global defaults for your entire
# application in settings: 
#
# LOGIN_REQUIRED_DEFAULT
# LOGIN_SESSION_KEY
# LOGIN_REDIRECT_LOCATION
#
class LoginRequiredMixin(object):

    # Whether the login is required for this view.
    # True for yes, None for maybe, false for None required
    login_required = settings.LOGIN_REQUIRED_DEFAULT 
    
    # Session Key used when logged in to determine if they
    # are logged in or not; you should not need to override
    # this as it's likely set site-wide, but if you're using
    # two completely separate user systems (e.g. customers,
    # back office) then you should subclass the mixin, set
    # it in the subclass, and then apply the mixin subclass to
    # your views, rather than override this in each of your
    # views.
    login_session_key = settings.LOGIN_SESSION_KEY_DEFAULT
    
    # Redirect Location to go when ensuring fails (see above
    # comment for login_session_key, it applies here)
    login_redirect_location = settings.LOGIN_REDIRECT_LOCATION_DEFAULT

    # What to do when you aren't logged in for a GET response
    # By default it will do an HTTP response redirect to the
    # redirect location
    def _get_if_not_logged_in(self, *args, **kwargs):
        return HttpResponseRedirect(self.login_redirect_location)

    # What to do when you aren't logged in for a POST response
    # By default it will do whatever _get_if_not_logged_in() does,
    # but a reasonable alternative might be to return an AJAX
    # redirect (see AjaxLoginRequiredMixin)
    def _post_if_not_logged_in(self, *args, **kwargs):
        return self._get_if_not_logged_in(*args, **kwargs)

    # This will check if you are logged in currently and
    # dispatch a type response if you are not.
    def _check_login(self, request, *args, **kwargs):
        if request.session.get(self.login_session_key) is None:
            method_name = '_'+request.method.lower()+'_if_not_logged_in'
            return getattr(self, method_name)(request = request, *args, **kwargs)

    # WARNING: Be very careful when overrideing this function.
    # This almost always needs to run first, so call super()
    # before doing something different.
    #
    # If the setting LOGIN_REQUIRED_DEFAULT is set to True,
    # or if you have said login_required is True in the
    # urls.py then it will check to see if you have a valid
    # login. If it does then continue normally, if not it will
    # try to return an appropriate redirect-ish response.
    #
    def dispatch(self, request, *args, **kwargs):
        if self.login_required == True:
            response = self._check_login(request = request, *args,**kwargs)
            if response:
                return response
        return super(LoginRequiredMixin, self).dispatch(request = request, *args, **kwargs)


# AjaxLoginRequiredMixin
#
# Almost identical to LoginRequiredMixin, but assumes a POST
# request is AJAX and thus needs an AJAX redirect if the user
# is not logged in.
#
class AjaxLoginRequiredMixin(LoginRequiredMixin):

    def _post_if_not_logged_in(self, *args, **kwargs):
        from sculpt.ajax.responses import AjaxRedirectResponse
        return AjaxRedirectResponse(self.login_redirect_location)
