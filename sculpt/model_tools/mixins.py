from django.apps import AppConfig
from django.contrib.auth.hashers import check_password, make_password, is_password_usable
from django.db import models
from sculpt.common import Enumeration
from sculpt.model_tools.hash_generator import ModelHashGenerator
import datetime

# Useful things to include in Model definitions

# a really simple convert-to-unicode method which
# is better than Django's default; good for
# prototyping, but a real class needs more
#
class SimpleUnicodeMixin(object):

    def __unicode__(self):
        if hasattr(self, 'title'):
            return u'[%(cls)s:%(id)s] %(title)s' % {
                    'cls': self.__class__.__name__,
                    'id': str(self.id),     # in case id is None, don't barf
                    'title': self.title,
                }
        else:
            return u'[%(cls)s:%(id)s]' % {
                    'cls': self.__class__.__name__,
                    'id': str(self.id),     # in case id is None, don't barf
                }

# AUTO-GENERATED HASH ID MODEL
#
# Often we want to expose a record ID to end users
# but doing so using Django's built-in id field has
# some disadvantages:
#
#   1. It exposes how many of a thing were present
#      in the system prior to that object's creation
#      (a business intelligence leak)
#
#   2. It is enumerable: it is trivial to write a
#      script that checks every possible ID, looking
#      for things that were inadequately protected
#      or are otherwise interesting (a privacy leak)
#
# The solution is to generate a unique hash, spreading
# the sequential id values "randomly" over a 256-bit
# hash space. This can then be returned to the user,
# as even with four billion entries in the system
# (2^32) there is only a 1 in 6.277e57 chance of any
# randomly-chosen hash matching a record in the system.
# (Roughly.)
#
# Some problems arise:
#
#   1. The hash must be unique, but the ID value is
#      typically not available when the hash needs to
#      be generated because it's a new record. This
#      means the hash MUST be generated from other
#      data, typically from the object, as well as the
#      datetime.
#
#   2. Generated hashes must be checked against the
#      database for uniqueness prior to being written;
#      this means there is a race condition where two
#      concurrent inserts of identical data may clash
#      and cause one to fail, even with the additional
#      checks.
#
#   3. Since hash generation data comes from outside
#      the field itself, this is a MODEL mix-in and not
#      just a simple field.
#
# You will need to define some additional values in the
# model in order for this to work:
#
#   AUTOHASH_SECRET - a string with unique data so that
#       hashes from different models aren't the same
#       (required)
#
#   AUTOHASH_FIELDS - a list of field names which will
#       be converted to strings, concatenated, and hashed
#       as one (required)
#
#   AUTOHASH_NO_DATETIME - if set to True, the current
#       datetime will not automatically be included in
#       the hash generation (default: False)
#
#   AUTOHASH_ALLOW_EMPTY - if set to False, empty or null
#       hash values will be populated before saving;
#       otherwise, they will only be generated when
#       generate_hash is specifically called (default: False)
#
class AutoHashMixin(object):
    
    # a convenient wrapper around the base ModelHashGenerator,
    # which automatically fetches all the input fields and
    # hands them off to be incorporated into the hash
    def generate_hash(self):
    
        # collect all the arguments together
        args = [ getattr(self, field) for field in self.AUTOHASH_FIELDS ]

        # include current timestamp unless we're directed not to
        if not getattr(self, 'AUTOHASH_NO_DATETIME', False):
            args.append(datetime.datetime.utcnow())

        # AUTOHASH_SECRET is required
        if self.AUTOHASH_SECRET is None:
            raise Exception('AUTOHASH_SECRET must be defined in your derived class. Refusing to operate without a defined secret.')

        # generate the hash and record it            
        self.hash = ModelHashGenerator.generate_hash(self.__class__, self.AUTOHASH_SECRET, *args)
        
    # override the model save method
    def save(self, *args, **kwargs):
    
        # if we're not allowing empty hashes, and this object
        # has an empty hash, fill it in right now
        if not getattr(self, 'AUTOHASH_ALLOW_EMPTY', False) and (self.hash == None or self.hash == ''):
            self.generate_hash()
            
        # pass through to the regular save method
        return super(AutoHashMixin, self).save(**kwargs)


# a URL pattern fragment to match hashes
AUTOHASH_URL_PATTERN = r'[-_0-9A-Za-z]{43}'
 
# LoginMixin
#
# Logging in doesn't have anything to do with authentication
# (determining who the user is) or authorization (determing
# whether a user is allowed to log in). Those steps should
# already be complete before logging in occurs. Logging in
# is all about recording an "active" user for a particular
# browser session, and logging out is all about breaking that
# association and scrubbing the session of any personalized
# data.
#
# Add this to a model to give it helper functions to work
# with request and session objects to manage the login
# process.
#
# OPTIONAL OVERRIDES:
#   LOGIN_ID_KEY - a string that is the key used to store
#       the ID of the user record into session
#   LOGIN_REQUEST_KEY - a string that is the Key used to
#       store the User instance into the request object
#
# NOTE: we define these two to be different from what
# Django's internal user management would be so that we can
# be logged in with both an app user and a Django user in
# the same session.
#
class LoginMixin(object):
    
    LOGIN_ID_KEY = 'app_user_id'
    LOGIN_REQUEST_KEY = 'app_user'

    # Sets the appropriate values in the session to stay logged in.
    def login(self, request):
        # Django Bug Fix
        # This is to force session_cache to load if it's not
        # already on the session object.
        request.session._get_session()

        # Enforce that you start at a clean slate
        request.session.cycle_key()
        request.session[self.LOGIN_ID_KEY] = self.pk

        # Cache the logged-in user object in the request (for
        # the remainder of this request)
        setattr(request, self.LOGIN_REQUEST_KEY, self)

    # In our login we are setting a key onto the request object
    # itself, and we need to clear that out, then call the super
    # which should get rid of the session
    @classmethod
    def logout(cls, request):
        setattr(request, cls.LOGIN_REQUEST_KEY, None)
        request.session.flush()

    # determine whether a session is logged in without making
    # an additional database request; we just test the ID of
    # the user record in the session
    @classmethod
    def is_logged_in(cls, request):
        value = False
        if cls.LOGIN_ID_KEY in request.session and cls.get_login_user_id(request) != None:
            value = True
        return value

    # fetch the currently-active user for a request
    #
    # This is checked first in the request object itself (in case
    # the user has already been fetched) and then, if an ID is
    # present in session but no user has been fetched, fetch it
    # from a database.
    #
    # NOTE: we use the default REQUEST and ID keys (attribute
    # names) to make life simple, but if you have an application
    # with multiple user classes (e.g. app user, back office user)
    # you will want to have different keys for these so that they
    # do not have any chance of overlapping. This allows you to
    # do easy checks (if Appuser.get_login_user(request) == None)
    # instead of constantly having to check the type of a returned
    # user, and allows you to add new non-overlapping classes of
    # users without revisiting existing code.
    #
    @classmethod
    def get_login_user(cls, request):
        # if we've already written the app_user to the request,
        # go ahead and return it without requiring an additional
        # database fetch
        if hasattr(request, cls.LOGIN_REQUEST_KEY):
            return getattr(request, cls.LOGIN_REQUEST_KEY)

        # Default the app_user to None if you are not logged in. The
        # following test could fail (because the session got flushed
        # but the request object's user was not removed) so we are
        # paranoid. Our own logout code DOES remove the object but
        # we'd rather be sure.
        setattr(request, cls.LOGIN_REQUEST_KEY, None)
        if cls.is_logged_in(request = request):
            # get the user if it exists, otherwise it's None;
            # cache the result in the request object
            setattr(request, cls.LOGIN_REQUEST_KEY, cls.get_login_user_queryset(request).first())
            return getattr(request, cls.LOGIN_REQUEST_KEY)

    # generate the queryset used to select users
    #
    # This allows you to customize the queryset without rewriting
    # all the login logic (e.g. if you wanted to always fetch some
    # related records, or apply other rules).
    #
    # It also gives you a base queryset for further expansion.
    #
    @classmethod
    def get_login_user_queryset(cls, request):
        return cls.objects.filter(pk = cls.get_login_user_id(request))

    # fetch just the ID of the logged-in user, if any
    # (automatically uses the correct key)
    @classmethod
    def get_login_user_id(cls, request):
        return request.session.get(cls.LOGIN_ID_KEY)

# PasswordMixin
#
# Includes functions that are useful in managing passwords
# that are stored locally as one-way hashes. This is
# intended for use in models derived from AbstractAppUserCredential.
# AbstractSimpleAppUser does not need this class because it
# derives from AbstractBaseUser, from which this is liberally
# cribbed.
#
# OPTIONAL OVERRIDES:
#   PASSWORD_FIELD - field name that contains the password hash;
#       defaults to "password" but should be overridden to "data2"
#       for AbstractAppUserCredential-derived classes.
#
# NOTE: From time to time Django updates the hashing functions used
# for passwords to make them stronger whenever weaknesses are found.
# However, since passwords are hashed it's not possible to upgrade
# the strength of all the password hashes at once, because the
# plaintext version of the password is not available. Django thus
# uses an opportunistic approach: whenever a password is tested,
# and a confirmed match is found, it will be updated in the database
# if it needs to be upgraded to a stronger algorithm. For this
# reason the check_password method MAY update the record behind the
# scenes. The set_password method, however, NEVER does this; you
# must explicitly save() the record after setting the password.
#
class PasswordMixin(object):

    PASSWORD_FIELD = 'password'

    def set_password(self, raw_password):
        setattr(self, self.PASSWORD_FIELD, make_password(raw_password))

    def check_password(self, raw_password):
        """
        Returns a boolean of whether the raw_password was correct. Handles
        hashing formats behind the scenes.
        """
        def setter(raw_password):
            self.set_password(raw_password)
            self.save(update_fields=[self.PASSWORD_FIELD])
        return check_password(raw_password, getattr(self, self.PASSWORD_FIELD), setter)

    def set_unusable_password(self):
        # Sets a value that will never be a valid hash
        setattr(self, self.PASSWORD_FIELD, make_password(None))

    def has_usable_password(self):
        return is_password_usable(getattr(self, self.PASSWORD_FIELD))

    # convenience wrapper, so passwords can be made during
    # object creation
    @classmethod
    def make_password(cls, raw_password):
        return make_password(raw_password)

# OverridableChoices
#
# Often in abstract base classes we need to provide an Enumeration
# of choices for a particular field, but we expect or require the
# concrete implementation to override this with an app-specific
# list. Django gets a bit confused by this because of how it builds
# fields incrementally from base classes on up. This is unhelpful.
#
# To fix this, we could simply reset the choice list every time we
# instantiate an object. This works, but Django's admin "add" pages
# generate their form based on the class object, not an instance
# object, so they won't see the updated choice list.
#
# It seems easy to just modify the choice list in the class object
# after it's been defined. The problem is that the mechanism for
# fetching the field (Foo._meta.get_field_by_name) isn't usable
# until the app registry is finished. Reproducing the logic here
# makes no sense.
#
# Instead, we take note of the request to update the model fields,
# listen for the class_prepared signal, and then update it. So,
# after a class is defined, call the method to register the update
# request, and it will happen automagically (ugh) once Django gets
# around to finishing the model loading.
#
#   class Foo(AbstractBaseClass):
#       ENUMERATION_NAME = Enumeration( ... )
#
#   Foo._register_field_choices('my_field', Foo.ENUMERATION_NAME)
#
# We call _register_field_choices for each affected field. The
# function itself is included in this mix-in.
#
# NOTE: you only have to do this if you actually override the
# enumeration from the base class's version. IF it's unchanged,
# you can skip this step.
#
# NOTE: YOU MUST ADD sculpt.model_tools TO YOUR INSTALLED_APPS
# SETTING or Django never finds the bit of code that acts on
# the registered changes after the app registry (and model
# loading) is complete.
#
class OverridableChoicesMixin(object):

    # This is a magical function.  In Django's internals, 
    # you can pull out a field and set various amount of data on it.
    # One use case would be to overrride the set choices from this 
    # abstract class with the values in the concrete class.
    # 
    # self will be your instance, a subclass of this class
    # self._meta is a piece of django's underbelly that 
    #     keeps the fields for a model
    # self.meta.get_field_by_name is a function that pulls out a tuple
    #     that looks like (<field>, None, Yes, No), which is why we ask 
    #     for [0] to get the field
    # self._meta.get_field_by_name(field_name)[0]._choices is the field 
    #     we want to override.  It has the values that the field is going
    #     to validate against when asked to clean.
    #
    # NOTE: we accept the actual choices OR an Enumeration.
    #
    @classmethod
    def _set_field_choices(cls, field_name, choices):
        if isinstance(choices, Enumeration):
            choices = choices.choices
        cls._meta.get_field_by_name(field_name)[0]._choices = choices

    @classmethod
    def _register_field_choices(cls, field_name, choices):
        field_choices[cls] = (field_name, choices)
    
# the signal handler that updates choices after classes are prepared    
field_choices = {}

class OverridableChoicesConfig(AppConfig):

    name = "sculpt.model_tools"
    verbose_name = "Code Sculpture Model Tools"

    def ready(self):
        for cls, args in field_choices.iteritems():
            cls._set_field_choices(*args)

# SimpleTreeMixin
#
# There are many ways to implement tree structures in SQL and various
# libraries for doing so. The simplest method is for each node to
# reference its parent and to include a display order value that
# applies amongst its siblings. This has the virtues of requiring only
# changes to immediate siblings when nodes are inserted or reordered
# and that moving whole sub-trees requires only a single field to be
# changed.
#
# The downside to this method is that fetching all the descendants of
# any particular node requires repeated queries to the database (one
# per generation) and fetching all the ancestors does also. There are
# schemes that optimize for that kind of query (such as the MPTT
# scheme) at the expense of increased cost of updates.
#
# We observe that the cost of updates, especially with large tree
# structures which may have multiple actively-modified areas at any
# given time, is nothing to sneer at. (Inserting a node and requiring
# 10,000 other nodes to be updated seems... unwise.) We also observe
# that with large trees it is unlikely that the whole tree would be
# presented to the user anyway, so being able to selectively limit
# the number of generations of children fetched is actually a good
# thing.
#
# To use this, you will need to define two fields within your class:
#
#   parent = models.ForeignKey('self', related_name = 'children', blank = True, null = True)
#   display_order = models.IntegerField(default = 0)
#
class SimpleTreeMixin(object):

    # get all ancestors, starting with the closest; if
    # oldest_first is True, returns the farthest ancestor
    # first instead (and it will return an iterator
    # instead of a bare list, use list() if you need to)
    #
    # NOTE: because of the way children fetching works, if
    # you locate the parents and then fetch the children
    # you will not get the same Python object that you
    # started with; you will get a copy of the same data
    # from the database in a new Python object.
    #
    def get_parents(self, oldest_first = False, stop_at_id = None):
        ancestors = []
        node = self
        while node.parent is not None and (stop_at_id is None or stop_at_id != node.pk):
            node = node.parent
            ancestors.append(node)

        if oldest_first:
            return reversed(ancestors)
        else:
            return ancestors

    # and a simpler, related question: is node A a
    # child of node B?
    def is_child_of(self, candidate_id, allow_self = True):
        # something is often considered a child of itself;
        # we test this first because get_parents will NOT
        # include self in the list, but WILL stop (with
        # an empty list) if self is the candidate
        if self.pk == candidate_id:
            return allow_self
        ancestors = self.get_parents(stop_at_id = candidate_id)
        return len(ancestors) > 0 and ancestors[-1].pk == candidate_id

    # get the root node
    #
    # Similar parent-then-child fetching caveat as
    # get_parents.
    #
    def get_root(self):
        if self.parent_id is None:
            return self
        else:
            return self.get_parents(oldest_first = True)[0]

    # get all siblings
    #
    # NOTE: this is cached on the parent object.
    #
    def get_siblings(self, q = None, order_by = None, select_related = None):
        return self.parent.get_children(q = q, order_by = order_by, select_related = select_related)
        
    # get immediate siblings
    #
    # Do these only if you need exactly one of these; if
    # you need more than one, it's likely more efficient
    # to use get_siblings() and work through the list.
    #
    def get_previous(self):
        return self.__class__.objects.filter(
                display_order_lt = self.display_order,
            ).order_by('-display_order').first()
        
    def get_next(self):
        return self.__class__.objects.filter(
                display_order_gt = self.display_order,
            ).order_by('display_order').first()
        
    # get children
    # 
    # You can specify the number of generations (-1 means
    # "all", but this is dangerous if you're not sure how
    # deep the rabbit hole goes), a Q object to filter
    # children, an alternative ordering, and whether each
    # node should automatically fetch related records.
    #
    # This is a class method, rather than an instance
    # method, because it's very, very common to want to
    # fetch the children for a list of nodes, not just
    # one, and it's much more efficient to fetch them
    # all at once. This method will fetch the children
    # for each node in the nodes list you pass and store
    # them in .children_list on each node; it will not
    # return a useful value.
    #
    @classmethod
    def fetch_children(cls, nodes, generations = 1, q = None, order_by = None, select_related = None):
        from sculpt.model_tools.tools import ModelTools
        
        # default sort order for children
        if order_by is None:
            order_by = [ 'display_order' ]

        # it's often useful to return a dictionary
        # of all the records fetched, indexed by
        # ID, and we can construct it easily as we
        # fetch; we'll also permit nodes to be a
        # dict instead of a list, in which case we
        # will write back to that dict
        if isinstance(nodes, dict):
            all_nodes = nodes
            nodes = nodes.values()

        else:
            all_nodes = dict([ (r.pk,r) for r in nodes ])
        
        # we test for equivalence to zero so that
        # -1 can be passed for "all" (dangerous;
        # if you know you need ALL nodes, not just
        # all the children starting at a particular
        # set of nodes, it's more efficient to use
        # fetch_all_children below)
        while generations != 0:
            generations -= 1
            
            # do the complete fetch
            ModelTools.fetch_related(nodes, 'children', q, order_by, select_related = select_related)
            
            # collect together all the fetched
            # nodes, which are dispersed among
            # the nodes we just queried about
            new_nodes = []
            for n in nodes:
                for ni in range(len(n.children_list)):
                    nn = n.children_list[ni]
                    # it's possible we fetched a
                    # node that we already had;
                    # make sure to de-duplicate
                    if nn.pk in all_nodes:
                        n.children_list[ni] = all_nodes[nn.pk]
                    else:
                        all_nodes[nn.pk] = nn

                    # if we don't already have
                    # a children_list on this node,
                    # we need to look it up in the
                    # next query
                    if not hasattr(nn, 'children_list'):
                        new_nodes.append(nn)
            
            if len(new_nodes) == 0:
                # no children were fetched; we can stop
                break
                
            nodes = new_nodes
            
        return all_nodes

    # and, as a special-case method, we allow fetching
    # the children of one specific node (ourselves)
    def get_children(self, generations = 1, q = None, order_by = None, select_related = None):
        return self.fetch_children([ self ], generations, q, order_by, select_related)

    # sometimes we know we want all the children, and we
    # want to fetch them all at once and then sort them
    # out
    #
    # NOTE: nodes can either be a Model class object, or
    # a list of Model instances; if a Model class object
    # is given, a list of root nodes will be returned
    #
    @classmethod
    def fetch_all_children(cls, nodes, q = None, order_by = None, select_related = None):

        # default sort order for children
        if order_by is None:
            order_by = [ 'display_order' ]
        
        # we need to identify the model to query
        if isinstance(nodes, models.Model):
            node_class = nodes
            node_ids = None
            nodes = None
            
        else:
            # if there are no nodes to fetch children for,
            # we can quit early
            if len(nodes) == 0:
                return
                
            node_class = nodes[0].__class__
            node_ids = [ n.id for n in nodes ]
            
        # fetch all the children
        children = node_class.objects.all()

        if node_ids:
            children = children.exclude(id__in = node_ids)  # don't re-fetch these parents

        if q is not None:
            children = children.filter(q)

        if order_by is not None:
            # a common mistake is to pass a single field name
            # instead of a list; catch this and rework it
            if isinstance(order_by, basestring):
                order_by = [ order_by ]
            children = children.order_by(*order_by)

        if select_related is not None:
            # a common mistake is to pass a single field name
            # instead of a list; catch this and rework it
            if isinstance(select_related, basestring):
                order_by = [ select_related ]
            children = children.select_related(*select_related)
        
        # create a quick index to all the children and
        # (if present) the original parents
        node_index = dict([ (n.id,n) for n in children ])
        if nodes is not None:
            node_index.update(dict([ (n.id,n) for n in nodes ]))    # add the parents to the index

        # now process all the children in order, assigning
        # them to their parents' children_list
        roots = []
        for n in children:
            n.children_list = []
            if n.parent_id is None:
                roots.append(n)
        
        for n in children:
            if n.parent_id is not None and n.parent_id in node_index:
                # only if we've fetched the parent; if we don't have
                # the parent it means the q parameter was too strict
                # and we omitted the parent when fetching "all" the
                # children, which will result in additional queries
                # when fetching the parent later (don't do that)
                
                # set object reference so Django doesn't load
                # duplicates for each child
                n.parent = node_index[n.parent_id]
                
                # add this node to the list of children, in order
                n.parent.children_list.append(n)
        
        return roots
