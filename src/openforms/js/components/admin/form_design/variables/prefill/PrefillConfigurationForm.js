import {Formik, useField, useFormikContext} from 'formik';
import PropTypes from 'prop-types';
import React, {useContext, useEffect, useState} from 'react';
import {FormattedMessage, useIntl} from 'react-intl';
import useUpdateEffect from 'react-use/esm/useUpdateEffect';

import {FormContext} from 'components/admin/form_design/Context';
import {SubmitAction} from 'components/admin/forms/ActionButton';
import Field from 'components/admin/forms/Field';
import Fieldset from 'components/admin/forms/Fieldset';
import FormRow from 'components/admin/forms/FormRow';
import Select, {LOADING_OPTION} from 'components/admin/forms/Select';
import SubmitRow from 'components/admin/forms/SubmitRow';
import {get} from 'utils/fetch';

import VariableMapping from '../../logic/actions/dmn/VariableMapping';
import {IDENTIFIER_ROLE_CHOICES} from '../constants';

const PrefillConfigurationForm = ({
  onSubmit,
  plugin = '',
  attribute = '',
  identifierRole = 'main',
  prefillOptions = {apiGroup: '', mappings: []},
  errors,
}) => {
  const [choices, setChoices] = useState([]);

  // XXX: we're not using formik's initialErrors yet because it doesn't support arrays of
  // error messages, which our backend *can* produce.
  // Taken from https://react.dev/reference/react/useEffect#fetching-data-with-effects
  useEffect(() => {
    let ignore = false;
    setChoices(null);
    const endpoint = `/api/v2/prefill/plugins/${plugin}/attributes`;
    // XXX: clean up error handling here at some point...
    get(endpoint).then(response => {
      if (!response.ok) throw response.data;
      if (!ignore) setChoices(response.data.map(attribute => [attribute.id, attribute.label]));
    });
    return () => {
      ignore = true;
    };
  }, []);

  const prefillAttributes = choices || LOADING_OPTION;

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
          {values.plugin === 'objects' ? (
            <ObjectsAPIPrefillFields
              prefillAttributes={prefillAttributes}
              values={values}
              errors={errors}
            />
          ) : (
            <PrefillFields prefillAttributes={prefillAttributes} errors={errors} />
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

const PrefillFields = ({prefillAttributes, errors}) => (
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

const ObjectsAPIPrefillFields = ({prefillAttributes, values, errors}) => {
  const intl = useIntl();
  const prefillAttributeLabel = intl.formatMessage({
    description: 'Accessible label for prefill attribute dropdown',
    defaultMessage: 'Prefill attribute',
  });

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

        <FormRow>
          <Field
            name="attribute"
            label={
              <FormattedMessage
                description="Objects API prefill API group label"
                defaultMessage="API group"
              />
            }
            errors={errors.apiGroup}
          >
            <AttributeField prefillAttributes={prefillAttributes} />
          </Field>
        </FormRow>
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
            mappingName="prefillOptions.mappings"
            targets={prefillAttributes}
            targetsFieldName="prefillAttribute"
            targetsColumnLabel={prefillAttributeLabel}
            selectAriaLabel={prefillAttributeLabel}
            cssBlockName="objects-prefill"
            alreadyMapped={values.prefillOptions.mappings.map(mapping => mapping.prefillAttribute)}
          />
        </FormRow>
      </Fieldset>
    </>
  );
};

export default PrefillConfigurationForm;
