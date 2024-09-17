import {Formik, useField, useFormikContext} from 'formik';
import PropTypes from 'prop-types';
import React, {useContext, useEffect, useState} from 'react';
import {FormattedMessage, useIntl} from 'react-intl';
import useAsync from 'react-use/esm/useAsync';
import useUpdateEffect from 'react-use/esm/useUpdateEffect';

import {FormContext} from 'components/admin/form_design/Context';
import {SubmitAction} from 'components/admin/forms/ActionButton';
import Field from 'components/admin/forms/Field';
import Fieldset from 'components/admin/forms/Fieldset';
import FormRow from 'components/admin/forms/FormRow';
import Select, {LOADING_OPTION} from 'components/admin/forms/Select';
import SubmitRow from 'components/admin/forms/SubmitRow';
import ErrorBoundary from 'components/errors/ErrorBoundary';
import {get} from 'utils/fetch';

import VariableMapping from '../../logic/actions/dmn/VariableMapping';
import ObjectTypeSelect from '../../registrations/objectsapi/fields/ObjectTypeSelect';
import ObjectTypeVersionSelect from '../../registrations/objectsapi/fields/ObjectTypeVersionSelect';
import ObjectsAPIGroup from '../../registrations/objectsapi/fields/ObjectsAPIGroup';
import {IDENTIFIER_ROLE_CHOICES} from '../constants';

const PrefillConfigurationForm = ({
  onSubmit,
  plugin = '',
  attribute = '',
  identifierRole = 'main',
  prefillOptions = {
    objectsApiGroup: '',
    objecttype: '',
    objecttypeVersion: null,
    variablesMapping: [],
  },
  errors,
}) => {
  return (
    <Formik
      initialValues={{
        plugin,
        attribute,
        identifierRole,
        prefillOptions,
      }}
      onSubmit={(values, actions) => {
        console.log(values);
        onSubmit(values);
        actions.setSubmitting(false);
      }}
    >
      {({handleSubmit, values}) => (
        <>
          {values.plugin === 'objects_api' ? (
            <ObjectsAPIPrefillFields plugin={plugin} values={values} errors={errors} />
          ) : (
            <PrefillFields plugin={plugin} errors={errors} />
          )}

          <SubmitRow>
            <SubmitAction
              onClick={event => {
                event.preventDefault();
                handleSubmit(event);
              }}
            />
          </SubmitRow>
        </>
      )}
    </Formik>
  );
};

PrefillConfigurationForm.propTypes = {
  onSubmit: PropTypes.func.isRequired,
  plugin: PropTypes.string,
  attribute: PropTypes.string,
  identifierRole: PropTypes.string,
  errors: PropTypes.shape({
    plugin: PropTypes.arrayOf(PropTypes.string),
    attribute: PropTypes.arrayOf(PropTypes.string),
    identifierRole: PropTypes.arrayOf(PropTypes.string),
  }).isRequired,
};

const PluginField = () => {
  const [fieldProps] = useField('plugin');
  const {setFieldValue} = useFormikContext();
  const {
    plugins: {availablePrefillPlugins},
  } = useContext(FormContext);

  const {value} = fieldProps;

  // reset the attribute value whenever the plugin changes
  useUpdateEffect(() => {
    setFieldValue('attribute', '');
  }, [setFieldValue, value]);

  const choices = availablePrefillPlugins.map(plugin => [plugin.id, plugin.label]);
  return <Select allowBlank choices={choices} id="id_plugin" {...fieldProps} />;
};

const AttributeField = ({prefillAttributes}) => {
  const [fieldProps] = useField('attribute');
  const {
    values: {plugin},
  } = useFormikContext();

  return (
    <Select
      allowBlank
      choices={prefillAttributes}
      id="id_attribute"
      disabled={!plugin}
      {...fieldProps}
    />
  );
};

const IdentifierRoleField = () => {
  const [fieldProps] = useField('identifierRole');
  const choices = Object.entries(IDENTIFIER_ROLE_CHOICES);
  return (
    <Select
      choices={choices}
      id="id_identifierRole"
      translateChoices
      capfirstChoices
      {...fieldProps}
    />
  );
};

const PrefillFields = ({plugin, errors}) => {
  // Load the possible prefill attributes
  // XXX: this would benefit from client-side caching
  const {
    loading,
    value = [],
    error,
  } = useAsync(async () => {
    if (!plugin) return [];

    const endpoint = `/api/v2/prefill/plugins/${plugin}/attributes`;
    // XXX: clean up error handling here at some point...
    const response = await get(endpoint);
    if (!response.ok) throw response.data;
    return response.data.map(attribute => [attribute.id, attribute.label]);
  }, [plugin]);

  // throw errors to the nearest error boundary
  if (error) throw error;
  const prefillAttributes = loading ? LOADING_OPTION : value;

  return (
    <Fieldset>
      <FormRow>
        <Field
          name="plugin"
          label={
            <FormattedMessage description="Variable prefill plugin label" defaultMessage="Plugin" />
          }
          errors={errors.plugin}
        >
          <PluginField />
        </Field>
      </FormRow>

      <FormRow>
        <Field
          name="attribute"
          label={
            <FormattedMessage
              description="Variable prefill attribute label"
              defaultMessage="Attribute"
            />
          }
          errors={errors.attribute}
        >
          <AttributeField prefillAttributes={prefillAttributes} />
        </Field>
      </FormRow>

      <FormRow>
        <Field
          name="identifierRole"
          label={
            <FormattedMessage
              description="Variable prefill identifier role label"
              defaultMessage="Identifier role"
            />
          }
          errors={errors.identifierRole}
        >
          <IdentifierRoleField />
        </Field>
      </FormRow>
    </Fieldset>
  );
};

const ObjectsAPIPrefillFields = ({plugin, values, errors}) => {
  const intl = useIntl();
  const {
    plugins: {availablePrefillPlugins},
  } = useContext(FormContext);
  const {setFieldValue} = useFormikContext();
  const objectsPlugin = availablePrefillPlugins.find(elem => elem.id === 'objects_api');
  const apiGroups = objectsPlugin.extra.apiGroups;

  const prefillAttributeLabel = intl.formatMessage({
    description: 'Accessible label for prefill attribute dropdown',
    defaultMessage: 'Prefill attribute',
  });

  const {objecttype, objecttypeVersion} = values.prefillOptions;

  // Load the possible prefill attributes
  // XXX: this would benefit from client-side caching
  const {
    loading,
    value = [],
    error,
  } = useAsync(async () => {
    if (!plugin || !objecttype || !objecttypeVersion) return [];

    const endpoint = `/api/v2/prefill/plugins/${plugin}/${objecttype}/versions/${objecttypeVersion}/attributes`;
    // XXX: clean up error handling here at some point...
    const response = await get(endpoint);
    if (!response.ok) throw response.data;
    return response.data.map(attribute => [attribute.id, attribute.label]);
  }, [plugin, objecttype, objecttypeVersion]);

  // throw errors to the nearest error boundary
  if (error) throw error;
  const prefillAttributes = loading ? LOADING_OPTION : value;

  return (
    <>
      <Fieldset>
        <FormRow>
          <Field
            name="plugin"
            label={
              <FormattedMessage
                description="Variable prefill plugin label"
                defaultMessage="Plugin"
              />
            }
            errors={errors.plugin}
          >
            <PluginField />
          </Field>
        </FormRow>

        {/* TODO copied from V2ConfigFields, should probably be reused */}
        <ObjectsAPIGroup
          prefix="prefillOptions"
          errors={errors['prefillOptions.apiGroup']}
          apiGroupChoices={apiGroups}
          onChangeCheck={() => {
            if (values.prefillOptions.variablesMapping.length === 0) return true;
            const confirmSwitch = window.confirm(
              intl.formatMessage({
                description:
                  'Objects API registration options: warning message when changing the api group',
                defaultMessage: `Changing the api group will remove the existing variables mapping.
                Are you sure you want to continue?`,
              })
            );
            if (!confirmSwitch) return false;
            setFieldValue('prefillOptions.variablesMapping', []);
            return true;
          }}
        />
        <ErrorBoundary
          errorMessage={
            <FormattedMessage
              description="Objects API registrations options: object type select error"
              defaultMessage="Something went wrong retrieving the available object types."
            />
          }
        >
          <ObjectTypeSelect
            prefix="prefillOptions"
            onChangeCheck={() => {
              if (values.prefillOptions.variablesMapping.length === 0) return true;
              const confirmSwitch = window.confirm(
                intl.formatMessage({
                  description:
                    'Objects API registration options: warning message when changing the object type',
                  defaultMessage: `Changing the objecttype will remove the existing variables mapping.
                  Are you sure you want to continue?`,
                })
              );
              if (!confirmSwitch) return false;
              setFieldValue('prefillOptions.variablesMapping', []);
              return true;
            }}
          />
        </ErrorBoundary>

        <ErrorBoundary
          errorMessage={
            <FormattedMessage
              description="Objects API registrations options: object type version select error"
              defaultMessage="Something went wrong retrieving the available object type versions."
            />
          }
        >
          <ObjectTypeVersionSelect prefix="prefillOptions" />
        </ErrorBoundary>
      </Fieldset>

      <Fieldset
        title={
          <FormattedMessage
            description="Objects API prefill mappings fieldset title"
            defaultMessage="Mappings"
          />
        }
      >
        <FormRow>
          <VariableMapping
            loading={false}
            mappingName="prefillOptions.variablesMapping"
            targets={prefillAttributes}
            targetsFieldName="prefillAttribute"
            targetsColumnLabel={prefillAttributeLabel}
            selectAriaLabel={prefillAttributeLabel}
            cssBlockName="objects-prefill"
            alreadyMapped={values.prefillOptions.variablesMapping.map(
              mapping => mapping.prefillAttribute
            )}
          />
        </FormRow>
      </Fieldset>
    </>
  );
};

export default PrefillConfigurationForm;
