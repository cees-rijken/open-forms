import PropTypes from 'prop-types';
import React, {useContext} from 'react';

import {FormContext} from 'components/admin/form_design/Context';

import {VARIABLE_SOURCES} from '../form_design/variables/constants';
import {SelectWithoutFormik} from './ReactSelect';

const allowAny = () => true;

const VariableSelection = ({
  id,
  name,
  value,
  onChange,
  includeStaticVariables = false,
  filter = allowAny,
  ...props
}) => {
  const {formSteps, formVariables, staticVariables} = useContext(FormContext);

  let formDefinitionsNames = {};
  formSteps.forEach(step => {
    formDefinitionsNames[step.formDefinition || step._generatedId] = step.internalName || step.name;
  });

  const allFormVariables = (includeStaticVariables ? staticVariables : []).concat(formVariables);

  const getVariableSource = variable => {
    if (variable.source === VARIABLE_SOURCES.userDefined) {
      return 'user variables';
    }
    if (variable.source === VARIABLE_SOURCES.component) {
      return 'component variables';
    }
    return 'static variables';
  };

  const choices = allFormVariables
    .filter(variable => filter(variable))
    .reduce(
      (variableGroups, variable) => {
        const label = formDefinitionsNames[variable.formDefinition]
        ? `${formDefinitionsNames[variable.formDefinition]}: ${variable.name} (${variable.key})`
        : `${variable.name} (${variable.key})`;

        variableGroups
          .find(group => group.label === getVariableSource(variable))
          .options.push({value: variable.key, label});
        return variableGroups;
      },
      [
        {label: 'user variables', options: []},
        {label: 'component variables', options: []},
        {label: 'static variables', options: []},
      ]
    );

  return (
    <SelectWithoutFormik
      id={id}
      className="form-variable-dropdown"
      name={name}
      options={choices}
      onChange={newValue => onChange({target: {name, value: newValue}})}
      value={value}
      {...props}
    />
  );
};

VariableSelection.propTypes = {
  id: PropTypes.string,
  name: PropTypes.string,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  includeStaticVariables: PropTypes.bool,
  filter: PropTypes.func,
};

export default VariableSelection;
