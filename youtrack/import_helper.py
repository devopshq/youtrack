# -*- coding: utf-8 -*-
from youtrack import YouTrackException


def utf8encode(source):
    if isinstance(source, str):
        source = source.encode('utf-8')
    return source


def _create_custom_field_prototype(connection, cf_type, cf_name, auto_attached=False, additional_params=None):
    if additional_params is None:
        additional_params = dict([])
    field = _get_custom_field(connection, cf_name)
    if field is not None:
        if field.type != cf_type:
            msg = "Custom field with name [ %s ] already exists. It has type [ %s ] instead of [ %s ]" % \
                  (utf8encode(cf_name), field.type, cf_type)
            raise LogicException(msg)
    else:
        connection.create_custom_field_detailed(cf_name, cf_type, False, True, auto_attached, additional_params)


def _get_custom_field(connection, cf_name):
    existing_fields = [item for item in connection.get_custom_fields() if utf8encode(item.name).lower() ==
                       utf8encode(cf_name).lower()]
    if len(existing_fields):
        return existing_fields[0]
    return None


def create_custom_field(connection, cf_type, cf_name, auto_attached, value_names=None, bundle_policy="0"):
    """
    Creates custom field prototype(if not exist) and sets default values bundle if needed

     Args:
        connection: An opened Connection instance.
        cf_type: Type of custom field to be created
        cf_name: Name of custom field that should be created (if not exists)
        auto_attached: If this field should be auto attached or not.
        value_names: Values, that should be attached with this cf by default.
                     If None, no bundle is created to this field, if empty, empty bundle is created.
        bundle_policy: ???
    Raises:
        LogicException: If custom field already exists, but has wrong type.
        YouTrackException: If something is wrong with queries.
    """
    if (value_names is None) and (not auto_attached or "[" not in cf_type):
        _create_custom_field_prototype(connection, cf_type, cf_name, auto_attached)
        return
    if value_names is None:
        value_names = set([])
    else:
        value_names = set(value_names)
    field = _get_custom_field(connection, cf_name)
    if field is not None:
        if hasattr(field, "defaultBundle"):
            bundle = connection.get_bundle(field.type, field.defaultBundle)
        elif field.autoAttached:
            return
        else:
            bundle = create_bundle_safe(connection, cf_name + "_bundle", cf_type)
    else:
        bundle = create_bundle_safe(connection, cf_name + "_bundle", cf_type)
        _create_custom_field_prototype(connection, cf_type, cf_name, auto_attached,
                                       {"defaultBundle": bundle.name,
                                        "attachBundlePolicy": bundle_policy})
    for value_name in value_names:
        try:
            connection.add_value_to_bundle(bundle, value_name)
        except YouTrackException:
            pass


#
#    values_to_add = calculate_missing_value_names(bundle, value_names)
#    [connection.addValueToBundle(bundle, name) for name in values_to_add]


#    if field is None:
#        bundle_name = cf_name + "_bundle"
#        _create_bundle_safe(connection, bundle_name, cf_type)
#        bundle = connection.getBundle(cf_type, bundle_name)
#        values_to_add = calculate_missing_value_names(bundle, value_names)
#
#
#        for value in values_to_add:
#            connection.addValueToBundle(bundle, value)
#
#


def process_custom_field(connection, project_id, cf_type, cf_name, value_names=None):
    """
    Creates custom field and attaches it to the project. If custom field already exists and has type
    cf_type it is attached to the project. If it has another type, LogicException is raised. If project field already
    exists, uses it and bundle from it. If not, creates project field and bundle with name
    <cf_name>_bundle_<project_id> for it.
    Adds value_names to bundle.
    Args:
        connection: An opened Connection instance.
        project_id: Id of the project to attach CF to.
        cf_type: Type of cf to be created.
        cf_name: Name of cf that should be created (if not exists) and attached to the project (if not yet attached)
        value_names: Values, that cf must have. If None, does not create any bundle for the field. If empty list,
                     creates bundle, but does not create any value_names in it. If bundle already contains
                     some value_names, only value_names that do not already exist are added.

    Raises:
        LogicException: If custom field already exists, but has wrong type.
        YouTrackException: If something is wrong with queries.
    """

    _create_custom_field_prototype(connection, cf_type, cf_name)
    if cf_type[0:-3] not in connection.bundle_types:
        value_names = None
    elif value_names is None:
        value_names = []

    existing_project_fields = [item for item in connection.getProjectCustomFields(project_id) if
                               utf8encode(item.name) == cf_name]
    if len(existing_project_fields):
        if value_names is None:
            return
        bundle = connection.getBundle(cf_type, existing_project_fields[0].bundle)
        values_to_add = calculate_missing_value_names(bundle, value_names)
    else:
        if value_names is None:
            connection.createProjectCustomFieldDetailed(project_id, cf_name, "No " + cf_name)
            return
        bundle = create_bundle_safe(connection, cf_name + "_bundle_" + project_id, cf_type)
        values_to_add = calculate_missing_value_names(bundle, value_names)
        connection.createProjectCustomFieldDetailed(project_id, cf_name, "No " + cf_name,
                                                    params={"bundle": bundle.name})
    for name in values_to_add:
        connection.addValueToBundle(bundle, bundle.createElement(name))


def add_values_to_bundle_safe(connection, bundle, values):
    """
    Adds values to specified bundle. Checks, whether each value already contains in bundle. If yes, it is not added.

    Args:
        connection: An opened Connection instance.
        bundle: Bundle instance to add values in.
        values: Values, that should be added in bundle.

    Raises:
        YouTrackException: if something is wrong with queries.
    """
    for value in values:
        try:
            connection.addValueToBundle(bundle, value)
        except YouTrackException as e:
            if e.response.status == 409:
                print("Value with name [ %s ] already exists in bundle [ %s ]" %
                      (utf8encode(value.name), utf8encode(bundle.name)))
            else:
                raise e


def create_bundle_safe(connection, bundle_name, bundle_type):
    bundle = connection.bundle_types[bundle_type[0:-3]](None, None)
    bundle.name = bundle_name
    try:
        connection.createBundle(bundle)
    except YouTrackException as e:
        if e.response.status == 409:
            print("Bundle with name [ %s ] already exists" % bundle_name)
        else:
            raise e
    return connection.getBundle(bundle_type, bundle_name)


def calculate_missing_value_names(bundle, value_names):
    bundle_elements_names = [elem.name.lower() for elem in bundle.values]
    return [value for value in value_names if value.lower() not in bundle_elements_names]


class LogicException(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)
