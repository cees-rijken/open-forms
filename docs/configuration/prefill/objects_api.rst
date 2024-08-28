.. _configuration_prefill_objects_api:

===========
Objects API
===========

`Objects API`_ can store objects which are defined (their schema and properties) in the `Objecttypes API`_.
With this prefill plugin we can have components/form fields which have pre-filled the values taken from the Objects API.

.. note::

   This service contains sensitive data and requires a connection to a specific
   client system. The forms which make use of this prefill plugin require DigiD/Eherkenning authentication
   of the user.

.. _`Objects API`: https://objects-and-objecttypes-api.readthedocs.io/en/latest/
.. _`Objecttypes API`: https://objects-and-objecttypes-api.readthedocs.io/en/latest/


Configuration
=============

1. In Open Forms, navigate to: **Forms**
2. Click **Add form**
3. Define the necessary form details and add the desired components
4. Navigate to: **Variables** tab
5. Navigate to: **User defined** subtab
6. Click **Add variable** and fill in the data from the available options:

   * **Plugin**: *Choose the Objects API plugin*
   * **API Group**: *Choose the desired API Group *
     (There must be at least one added-configured via **Miscellaneous** > **Objects API groups**)
   * **Objecttype**: *Based on the selected API group above, you can choose the objecttype from the auto populated list*
   * **Mappings**: *On the left we have the available form variables and on the right the available attributes which are
     defined in the selected objecttype's schema properties. You can do the mappings accordingly*
   
7. Click **Save**
8. Save the form

The Objects API configuration is now complete.


