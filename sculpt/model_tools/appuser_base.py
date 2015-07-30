from django.db import models
from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from sculpt.ajax.enumerations import ISO_COUNTRIES
from sculpt.common import Enumeration, EnumerationData
from sculpt.model_tools.base import AbstractAutoHash
from sculpt.model_tools.mixins import AutoHashMixin, LoginMixin, OverridableChoicesMixin

import datetime

# Django's auth module contains a User model. With
# recent versions it's finally possible to work around
# its limitations, but if you don't want to use and
# extend Django's built-in User system, you need to
# build user models based on something else. These
# abstract base classes provide one such starting
# point.
#
# Reasons you might not want to use Django's User
# models:
#
# 1. Django's user system is linked to the Django
# admin app. This means your app's users are in the
# same system as the tool that offers extremely low-
# level access to your database. Obviously you protect
# access to this, but ask yourself which is a more
# likely and harder-to-spot programming mistake:
# failing to notice that a session is linked to a
# user AT ALL, or failing to correctly parse which
# level of access a particular user happens to have?
#
# 2. You might have a lot of users and you just don't
# want to try to put those users into Django's User
# database, where it's harder to figure out who is
# supposed to have access and who is not.
#
# 3. You are building an app for a client, and when
# you are done, you need to hand off user management
# for the application to the client, but you largely
# do not expect them to be mucking around with the
# Django admin tool. It's much easier to build tools
# that work with completely separate models than to
# make tools that check whether they're allowed to
# modify specific records.
#
# These are brief summaries and this isn't intended
# as a universal condemnation of full integration
# with Django's User system. The point is to get you
# to think about your user management rather than
# adopt a default solution that might work against
# you later.
#
# If you choose to create a separate user system,
# two common patterns are supported. "Simple" app
# users assume that each user has exactly one username
# and password that can be used to authenticate,
# and this is derived from Django's AbstractBaseUser
# in order to pick up its password-handling ability.
# The other pattern separates credentials from the
# user, so that you can support multiple authentication
# schemes for the same account (e.g. initially creating
# an account with a username/password and then later
# linking it to a Facebook account). It's more work
# but more flexible.
#
# No matter which you choose, they will pick up both
# the LoginMixin and AbstractAutoHash mixins.

""" SIMPLE APP USER SETUP """

# AbstractSimpleAppUser
#
# REQUIRED OVERRIDES:
#   - AUTOHASH_SECRET - a unique string (AbstractAutoHash)
#
# OPTIONAL OVERRIDES:
#   - AUTOHASH_FIELDS - fields used to generate hash (AbstractAutoHash)
#   - CHECK_PASSWORD_METHOD - the name of the function used to check
#       passwords (AbstractBaseUser)
#   - REQUIRED_FIELDS - indicates which fields are required
#       (AbstractBaseUser)
#
# Description:
#   This is to abstract out the most common features
#   of an App User. This class represents the most
#   basic logins, where the only way to authenticate
#   would be a username and password (always). It is
#   easier to implement than the multiple-auth scheme
#   user.
#
#   This model REQUIRES that usernames be unique. If
#   you have a situation that allows users to be
#   deleted, you need to have a strategy for dealing
#   with usernames if you do not want the default
#   behavior this restriction implies (that once used,
#   a username is gone forever).
#
class AbstractSimpleAppUser(LoginMixin, AbstractAutoHash, AbstractBaseUser):
    class Meta(AbstractBaseUser.Meta):
        abstract = True

    # AbstractBaseUser settings
    CHECK_PASSWORD_METHOD = 'check_password'
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = [ 'username' ]

    # AutoHashMixin settings
    AUTOHASH_FIELDS = [ 'username' ]

    # actual fields on this model
    username = models.CharField(max_length = 32, unique = True)

    # validate a username and password, returning
    # the matched user or None
    # NOTE: it always filters on the value from USERNAME_FIELD
    @classmethod
    def authenticate(cls, username, password):
        user = cls.objects.filter(**{ cls.USERNAME_FIELD: username }).first()
        if user is not None and hasattr(user, cls.CHECK_PASSWORD_METHOD) and getattr(user,cls.CHECK_PASSWORD_METHOD)(password):
            return user


""" COMPLEX APP USER SETUP """

# AbstractAppUser
#
# REQUIRED OVERRIDES:
#   - AUTOHASH_SECRET - a unique string (AbstractAutoHash)
#   - authenticate - method used to authenticate a user,
#       typically by knowing which authentication method
#       is expected, and checking against credentials of
#       that type
#
# OPTIONAL OVERRIDES:
#   - AUTOHASH_FIELDS - fields used to generate hash (AbstractAutoHash)
#
# Description:
#   Unlike AbstractSimpleAppUser, this class is for users
#   that could be authenticated by any of several means.
#   For example, by username and password, or by Facebook
#   token, or by Twitter token, or by unique device ID.
#   Most of the heavy-lifting is done in the Credentials
#   class, leaving this an empty shell. You will still want
#   to add fields that describe your users.
#
class AbstractAppUser(LoginMixin, AbstractAutoHash, models.Model):
    class Meta(object):
        abstract = True

    @classmethod
    def authenticate(cls, type, *args, **kwargs):
        """ MUST OVERRIDE """
        raise Exception("this function must be overridden")


# AbstractAppUserCredential
#
# SUGGESTED CODE IN SUBCLASS:
#   - appuser = models.ForeignKey(<class Child(AbstractAppUser)>, related_name = 'credentials')
#
# REQUIRED OVERRIDES:
#   - CREDENTIAL_TYPES - Enumeration or Tuple
#   - authenticate() - function - each instance of a credential should be able to authenticate itself to see if it's valid.
#
# Description:
#   This represents a single set of credentials for a user,
#   and connects to the code for validating those
#   credentials.
#
class AbstractAppUserCredential(OverridableChoicesMixin, models.Model):
    class Meta(object):
        abstract = True

    CREDENTIAL_TYPES = Enumeration() # Expects to be enumeration

    data1 = models.CharField(max_length = 255, blank = True, null = True)  # typically a username or user ID
    data2 = models.CharField(max_length = 255, blank = True, null = True)  # typically a hashed password or auth token
    credential_type = models.IntegerField(choices = CREDENTIAL_TYPES.choices)
    credential_type_data = property(EnumerationData('CREDENTIAL_TYPES', 'credential_type'))

    # We are running the init function to override the credential type choices
    def __init__(self, *args, **kwargs):
        super(AbstractAppUserCredential, self).__init__(*args, **kwargs)
        self._set_field_choices(field_name = 'credential_type', choices = self.CREDENTIAL_TYPES.choices)

    # This function is used to identify if your current user is permitted to do an action.
    # Most commonly used in login to ensure that a user is allowed to come into the site
    # RETURN Boolean
    def authenticate(self, user):
        """ MUST OVERRIDE """
        raise Exception("this function must be overridden")


# Contact Information
#
# This is a very common pattern, so we set these up once and re-use
# them in multiple apps. Addresses should always be prepared to handle
# international locations.
#
# Generally when you create a concrete implementation of this class
# you will add foreign keys to the things that may have contact info
# associated with them (e.g. something derived from AbstractAppUser).
# However, if you are absolutely certain that a record only needs one
# contact info object, you can construct the relationship from the
# other direction.
#
class AbstractContactInfo(OverridableChoicesMixin, models.Model):
    class Meta(object):
        abstract = True
    
    # does this address have a name or label?
    # (if not, we use the address type)
    title = models.CharField(max_length = 30, blank = True, null = True)

    # by default we will take the country list as the ISO country list
    COUNTRIES = ISO_COUNTRIES
    
    # all fields optional
    address1 = models.CharField(max_length = 100, blank = True, null = True)
    address2 = models.CharField(max_length = 100, blank = True, null = True)
    address3 = models.CharField(max_length = 100, blank = True, null = True)    # primarily international
    city     = models.CharField(max_length = 100, blank = True, null = True)
    state    = models.CharField(max_length =  50, blank = True, null = True)    # or province
    zip      = models.CharField(max_length =  50, blank = True, null = True)    # or postal code
    country  = models.CharField(max_length =   2, blank = True, null = True, choices = COUNTRIES.choices, default = 'US')    # ISO 3166-1-alpha-2; see http://en.wikipedia.org/wiki/ISO_3166-1_alpha-2
    country_data = property(EnumerationData('COUNTRIES','country'))

    # what type of address is it?
    # NOTE: actual concrete implementations may want to override
    # this list with a subset/superset
    ADDRESS_TYPES = Enumeration(
            (0, 'BILLING', 'Billing'),
            (1, 'SHIPPING', 'Shipping'),
        )
    address_type = models.IntegerField(choices = ADDRESS_TYPES.choices, default = 0)
    address_type_data = property(EnumerationData('ADDRESS_TYPES','address_type'))

    # what is the display order/preference?
    # we use this to determine a "best" address for a person
    display_order = models.IntegerField(default = 0)

    # handle overridable enumerations
    def __init__(self, *args, **kwargs):
        super(AbstractContactInfo, self).__init__(*args, **kwargs)
        self._set_field_choices(field_name = 'country', choices = self.COUNTRIES)
        self._set_field_choices(field_name = 'address_type', choices = self.ADDRESS_TYPES)


# Phone Number
#
# You will need to add foreign keys when you create a concrete
# implementation. Depending on your data model, you may want to
# create foreign keys to something derived from AbstractContactInfo
# (if phone numbers are associated most closely with an address)
# or something from AbstractAppUser (if phone numbers are associated
# most closely with a person).
#
class AbstractPhoneNumber(OverridableChoicesMixin, models.Model):
    class Meta(object):
        abstract = True

    # does this number have a name or label?
    # (if not, we use the number type)
    title = models.CharField(max_length = 30, blank = True, null = True)
    
    # what is the actual number?
    number = models.CharField(max_length = 30)
    
    # what type of number is it?
    # NOTE: actual concrete implementations may want to override
    # this list with a subset
    NUMBER_TYPES = Enumeration(
            (0, 'UNKNOWN', 'Unknown'),
            (1, 'HOME', 'Home'),
            (2, 'WORK', 'Work'),
            (3, 'CELL', 'Cell/Mobile'),
            (4, 'FAX', 'Fax'),
        )
    number_type = models.IntegerField(choices = NUMBER_TYPES.choices, default = NUMBER_TYPES.UNKNOWN)
    number_type_data = property(EnumerationData('NUMBER_TYPES','number_type'))
    
    # are there additional notes about when this number can
    # be called or special instructions?
    notes = models.CharField(max_length = 100, blank = True, null = True)

    # what is the display order/preference?
    # we use this to determine a "best" number for a person
    display_order = models.IntegerField(default = 0)

    # handle overridable enumerations
    def __init__(self, *args, **kwargs):
        super(AbstractPhoneNumber, self).__init__(*args, **kwargs)
        self._set_field_choices(field_name = 'number_type', choices = self.NUMBER_TYPES)


# a base email address class that can track its validation
# state; derive from the class and provide any additional
# foreign keys required for your app
class AbstractEmail(OverridableChoicesMixin, models.Model):
    class Meta(object):
        abstract = True

    VERIFICATION_STATES = Enumeration(
            (-3, 'BLOCKED'),       ## Owner opted out of all emails (**** needs implementing)
            (-2, 'VALID'),         ## Known Good
            (-1, 'INVALID'),       ## Known Bad
            ( 0, 'UNVERIFIED'),    ## link sent, awaiting response
            # ... more in-progress unverified states
        )

    address = models.CharField(max_length = 254, db_index = True)    # intentionally long, but MUST BE INDEXED
    status = models.IntegerField(choices = VERIFICATION_STATES.choices)
    status_data = property(EnumerationData('VERIFICATION_STATES','status'))

    # when is this record vreated?
    date_created = models.DateTimeField(auto_now = False, auto_now_add = False, default = datetime.datetime.utcnow)
    # when is this validated by the end user?
    date_validated  = models.DateTimeField(auto_now = False, auto_now_add = False, blank = True, null = True)

    # handle overridable enumerations
    def __init__(self, *args, **kwargs):
        super(AbstractEmail, self).__init__(*args, **kwargs)
        self._set_field_choices(field_name = 'status', choices = self.VERIFICATION_STATES)

    # a helper method to automatically mark an email address as
    # verified and mark all other copies of the same address as
    # invalid
    #
    # NOTE: if your derived class overrides VERIFICATION_STATES
    # such that VALID is renamed or renumbered, you will want
    # to override this method; better yet, don't rename VALID
    #
    # NOTE: unless you pass save = False, this will update the
    # database
    #
    def mark_as_valid(self, save = True):
        # first, update ourselves
        self.status = self.VERIFICATION_STATES.VALID
        self.date_validated = datetime.datetime.utcnow()
        if save:
            self.save(update_fields = [ 'status', 'date_validated' ])

        # second, look for other records in UNVERIFIED
        self.__class__.objects.filter(
                address = self.address, status = self.VERIFICATION_STATES.UNVERIFIED,
            ).exclude(
                id = self.id,
            ).update(
                status = self.VERIFICATION_STATES.INVALID,
            )


# AbstractMultipleEmail
#
# Although the base AbstractEmail class is designed so that it
# can be used as a one-to-many (multiple email addresses per
# other thing, such as user) there's still an assumption that
# there is probably "one" email address, and we support multiple
# in order to ease the transition. In cases where we have true
# multiple-email-address support we need to have labels and
# preferences for those email addresses, similar to how we have
# them for addresses and phone numbers.
#
class AbstractMultipleEmail(AbstractEmail):
    class Meta(object):
        abstract = True

    # does this number have a name or label?
    title = models.CharField(max_length = 30, blank = True, null = True)
    
    # what is the display order/preference?
    # we use this to determine a "best" address for a person
    display_order = models.IntegerField(default = 0)


# Web Sites
#
# Sometimes we want to associate web site address(es) with
# users or entities. This is a base class for doing so.
#
class AbstractWebSite(models.Model):
    class Meta(object):
        abstract = True

    # does this number have a name or label?
    title = models.CharField(max_length = 30, blank = True, null = True)

    # what is the actual web site?
    # NOTE: we don't make this a Django URLField because
    # we don't want their validation rules.
    url = models.CharField(max_length = 250)
    
    # what is the display order/preference?
    # we use this to determine a "best" address for a person
    display_order = models.IntegerField(default = 0)

