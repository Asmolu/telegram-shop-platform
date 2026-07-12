import { describe, expect, it } from 'vitest';
import { ApiClientError } from '../shared/api/client';
import { mapCheckoutApiValidationErrors, validateCheckoutForm } from './checkoutValidation';

describe('checkout validation', () => {
  it('returns field-specific errors for empty and invalid required values', () => {
    expect(validateCheckoutForm({ contactName: '', phone: '', deliveryMethod: '', city: '', height: 'x', weight: 'x' })).toEqual({
      contactName: 'Укажите получателя.', phone: 'Укажите номер телефона.',
      deliveryMethod: 'Выберите способ доставки.', city: 'Укажите адрес доставки.',
      height: 'Укажите рост числом в сантиметрах.', weight: 'Укажите вес числом в килограммах.',
    });
  });

  it('maps multiple FastAPI validation locations without exposing messages', () => {
    const error = new ApiClientError({ message: 'Field required', status: 422, kind: 'validation', details: {
      detail: [
        { loc: ['body', 'contact_name'], msg: 'Field required', type: 'missing' },
        { loc: ['body', 'weight_kg'], msg: 'Input should be valid', type: 'decimal_parsing' },
      ],
    } });
    expect(mapCheckoutApiValidationErrors(error)).toEqual({
      contactName: 'Укажите получателя.', weight: 'Укажите вес числом в килограммах.',
    });
  });

  it('uses an empty safe mapping for unknown validation fields', () => {
    const error = new ApiClientError({ message: 'technical', status: 422, kind: 'validation', details: { detail: [{ loc: ['body', 'unknown'] }] } });
    expect(mapCheckoutApiValidationErrors(error)).toEqual({});
  });
});
