import {Formio} from 'react-formio';

import {DEFAULT_VALUE} from './edit/options';
import {
  ADVANCED,
  DEFAULT_PASSWORD_TABS,
  REGISTRATION,
  SENSITIVE_PASSWORD,
  TRANSLATIONS,
  VALIDATION,
} from './edit/tabs';

class PasswordField extends Formio.Components.components.password {
  static editForm() {
    return {
      components: [
        {
          ...DEFAULT_PASSWORD_TABS,
          components: [
            {
              ...SENSITIVE_PASSWORD,
              components: SENSITIVE_PASSWORD.components.filter(
                option => option.key !== DEFAULT_VALUE.key
              ),
            },
            ADVANCED,
            VALIDATION,
            REGISTRATION,
            TRANSLATIONS,
          ],
        },
      ],
    };
  }
}

export default PasswordField;
