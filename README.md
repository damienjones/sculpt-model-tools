sculpt-model-tools
==================

Django's ORM is a big, gnarly, awesome beast. It's very powerful but, since it has evolved from more humble beginnings, it is also somewhat baroque, and there are useful, repetitive tasks that it does not automate. This library fills in some of those gaps.

Features
--------

* ModelTools - a helper class for making certain kinds of queries:
    * fetch_related - fetches related objects for all of the objects in a query set and automatically sorts them out, building a list for each of the original objects. This is similar to Django 1.4's prefetch_related, but more flexible because you can filter and sort the results.
    * update_or_create - similar to Django 1.7's update_or_create, but separates updates from defaults. (Assuming that any field that requires a default must be reset to that default is, frankly, dumb.)
    * dirty tracking - allows model objects to be updated and automatically flagged as dirty only if they've changed, along with an easy save_if_dirty method.
* OneToOneReverse - a helper class to resolve a Django quirk with regards to one-to-one relationships (the reverse side throws an exception if there is no matching record, instead of just returning None).
* set_isolation_mode - for those times when you really, really need to manipulate the SQL isolation mode of your transaction.
* AbstractSoftDelete - an abstract base model class that refuses delete() calls but includes a _date_deleted_ field to track when it was marked for deletion.
* AutoHashModel - an abstract base model class that automatically generates a 256-bit hash when new records are created, based on the fields specified in the class.
* LoginMixin - can be added to a model to give it helper functions to record itself in a request session.
* PasswordMixin - can be added to a model to give it password management functions like Django's user class.
* OverridableChoices - allows base classes to specify a default Enumeration for a field and then a derived class can replace it with a different enumeration.
    