import {createTypeCheck} from '@open-formulieren/formio-builder';
import _ from 'lodash';
import PropTypes from 'prop-types';
import React, {useContext, useState} from 'react';
import {FormattedMessage, useIntl} from 'react-intl';

import {FormContext} from 'components/admin/form_design/Context';
import RegistrationBackendSelection from 'components/admin/form_design/RegistrationBackendSelection';
import StepSelection from 'components/admin/form_design/StepSelection';
import DSLEditorNode from 'components/admin/form_design/logic/DSLEditorNode';
import {
  MODIFIABLE_PROPERTIES,
  STRING_TO_TYPE,
  TYPE_TO_STRING,
} from 'components/admin/form_design/logic/constants';
import ServiceFetchConfigurationPicker from 'components/admin/form_design/variables/ServiceFetchConfigurationPicker';
import ActionButton from 'components/admin/forms/ActionButton';
import ComponentSelection from 'components/admin/forms/ComponentSelection';
import JsonWidget from 'components/admin/forms/JsonWidget';
import Select from 'components/admin/forms/Select';
import VariableSelection from 'components/admin/forms/VariableSelection';
import Modal from 'components/admin/modals/Modal';

import {ActionError, Action as ActionType} from './types';

const ActionProperty = ({action, errors, onChange}) => {
  const modifiablePropertyChoices = Object.entries(MODIFIABLE_PROPERTIES).map(([key, info]) => [
    key,
    info.label,
  ]);

  const castValueTypeToString = action => {
    const valueType = action.action.property.type;
    const value = action.action.state;
    return TYPE_TO_STRING[valueType](value);
  };

  const castValueStringToType = value => {
    const valueType = action.action.property.type;
    return STRING_TO_TYPE[valueType](value);
  };

  return (
    <>
      <DSLEditorNode errors={errors.component}>
        <ComponentSelection name="component" value={action.component} onChange={onChange} />
      </DSLEditorNode>
      <DSLEditorNode errors={errors.action?.property?.value}>
        <Select
          name="action.property"
          choices={modifiablePropertyChoices}
          translateChoices
          allowBlank
          onChange={e => {
            const propertySelected = e.target.value;
            const fakeEvent = {
              target: {
                name: e.target.name,
                value: {
                  type: MODIFIABLE_PROPERTIES[propertySelected]?.type || '',
                  value: propertySelected,
                },
              },
            };
            onChange(fakeEvent);
          }}
          value={action.action.property.value}
        />
      </DSLEditorNode>
      {MODIFIABLE_PROPERTIES[action.action.property.value] && (
        <DSLEditorNode errors={errors.action?.state}>
          <Select
            name="action.state"
            choices={MODIFIABLE_PROPERTIES[action.action.property.value].options}
            translateChoices
            allowBlank
            onChange={event => {
              onChange({
                target: {
                  name: event.target.name,
                  value: castValueStringToType(event.target.value),
                },
              });
            }}
            value={castValueTypeToString(action)}
          />
        </DSLEditorNode>
      )}
    </>
  );
};

const ActionVariableValue = ({action, errors, onChange}) => {
  const formContext = useContext(FormContext);
  const infer = createTypeCheck(formContext);
  // check the expression and the picked variable are of the same type
  const validateJsonLogic = expression => infer({'===': [{var: action.variable}, expression]});
  return (
    <>
      <DSLEditorNode errors={errors.variable}>
        <VariableSelection name="variable" onChange={onChange} value={action.variable} />
      </DSLEditorNode>
      <DSLEditorNode errors={errors.action?.value}>
        <JsonWidget
          name="action.value"
          logic={action.action.value}
          onChange={onChange}
          validateJsonLogic={validateJsonLogic}
        />
      </DSLEditorNode>
    </>
  );
};

const ActionFetchFromService = ({action, errors, onChange}) => {
  const intl = useIntl();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const closeModal = () => {
    setIsModalOpen(false);
  };

  const formContext = useContext(FormContext);

  const serviceFetchConfigFromVar =
    _.cloneDeep(formContext.formVariables.find(element => element.key === action.variable))
      ?.serviceFetchConfiguration || undefined;

  if (serviceFetchConfigFromVar) {
    if (!Array.isArray(serviceFetchConfigFromVar.headers)) {
      serviceFetchConfigFromVar.headers = Object.entries(serviceFetchConfigFromVar.headers || {});
    }

    if (!Array.isArray(serviceFetchConfigFromVar.queryParams)) {
      serviceFetchConfigFromVar.queryParams = Object.entries(
        serviceFetchConfigFromVar.queryParams || {}
      );
    }

    switch (serviceFetchConfigFromVar.dataMappingType) {
      case 'JsonLogic':
        serviceFetchConfigFromVar.jsonLogicExpression = serviceFetchConfigFromVar.mappingExpression;
        break;
      case 'jq':
        serviceFetchConfigFromVar.jqExpression = serviceFetchConfigFromVar.mappingExpression;
        break;
      default:
        serviceFetchConfigFromVar.jqExpression = serviceFetchConfigFromVar.mappingExpression;
    }
  }

  const actionButtonId = `open_service_fetch_modal_for_${action.variable}`;
  return (
    <>
      <DSLEditorNode errors={errors.variable}>
        <VariableSelection
          name="variable"
          value={action.variable}
          onChange={onChange}
          // Only values of user defined values can be set
          filter={variable => variable.source === 'user_defined'}
        />
      </DSLEditorNode>
      <DSLEditorNode errors={errors.action?.value}>
        <label className="required" htmlFor={actionButtonId}>
          <FormattedMessage
            description="Currently selected service fetch configuration label"
            defaultMessage="Fetch configuration:"
          />
        </label>
        {serviceFetchConfigFromVar?.name ||
          intl.formatMessage({
            description: 'No service fetch configuration configured yet message',
            defaultMessage: '(not configured yet)',
          })}
        <ActionButton
          id={actionButtonId}
          name="_open_service_fetch_modal"
          onClick={event => {
            event.preventDefault();
            setIsModalOpen(true);
          }}
          text={intl.formatMessage({
            description: 'Button to open service fetch configuration modal',
            defaultMessage: 'Configure',
          })}
        />
      </DSLEditorNode>

      <Modal
        isOpen={isModalOpen}
        closeModal={closeModal}
        title={
          <FormattedMessage
            description="Service fetch configuration selection modal title"
            defaultMessage="Service fetch configuration"
          />
        }
        contentModifiers={['with-form', 'large']}
      >
        <ServiceFetchConfigurationPicker
          initialValues={serviceFetchConfigFromVar}
          variableName={action.variable}
          onFormSave={closeModal}
          onChange={onChange}
        />
      </Modal>
    </>
  );
};

const ActionStepNotApplicable = ({action, errors, onChange}) => {
  return (
    <DSLEditorNode errors={errors.formStepUuid}>
      <StepSelection name="formStepUuid" value={action.formStepUuid} onChange={onChange} />
    </DSLEditorNode>
  );
};

const ActionStepApplicable = ({action, errors, onChange}) => {
  return (
    <DSLEditorNode errors={errors.formStepUuid}>
      <StepSelection name="formStepUuid" value={action.formStepUuid} onChange={onChange} />
    </DSLEditorNode>
  );
};

const ActionSetRegistrationBackend = ({action, errors, onChange}) => {
  return (
    <DSLEditorNode errors={errors.value}>
      <RegistrationBackendSelection
        name="action.value"
        value={action.action.value}
        onChange={onChange}
      />
    </DSLEditorNode>
  );
};

const ActionComponent = ({action, errors, onChange}) => {
  let Component;
  switch (action.action.type) {
    case 'property': {
      Component = ActionProperty;
      break;
    }
    case 'variable': {
      Component = ActionVariableValue;
      break;
    }
    case 'fetch-from-service': {
      Component = ActionFetchFromService;
      break;
    }
    case '':
    case 'disable-next': {
      return null;
    }
    case 'step-not-applicable': {
      Component = ActionStepNotApplicable;
      break;
    }
    case 'step-applicable': {
      Component = ActionStepApplicable;
      break;
    }
    case 'set-registration-backend': {
      Component = ActionSetRegistrationBackend;
      break;
    }
    default: {
      throw new Error(`Unknown action type: ${action.action.type}`);
    }
  }

  return <Component action={action} errors={errors} onChange={onChange} />;
};

ActionComponent.propTypes =
  ActionProperty.propTypes =
  ActionVariableValue.propTypes =
  ActionFetchFromService.propTypes =
  ActionStepNotApplicable.propTypes =
    {
      action: ActionType.isRequired,
      errors: ActionError,
      onChange: PropTypes.func.isRequired,
    };

export {ActionComponent};
