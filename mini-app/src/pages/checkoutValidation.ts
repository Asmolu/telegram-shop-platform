import { ApiClientError } from '../shared/api/client';

export type CheckoutField = 'contactName' | 'phone' | 'deliveryMethod' | 'city' | 'height' | 'weight';
export type CheckoutFieldErrors = Partial<Record<CheckoutField, string>>;

const messages: Record<CheckoutField, string> = {
  contactName: 'Укажите получателя.',
  phone: 'Укажите номер телефона.',
  deliveryMethod: 'Выберите способ доставки.',
  city: 'Укажите адрес доставки.',
  height: 'Укажите рост числом в сантиметрах.',
  weight: 'Укажите вес числом в килограммах.',
};

const backendFields: Record<string, CheckoutField> = {
  contact_name: 'contactName', contact_phone: 'phone', delivery_method: 'deliveryMethod',
  delivery_address: 'city', height_cm: 'height', weight_kg: 'weight',
};

export function validateCheckoutForm(values: Record<CheckoutField, string>): CheckoutFieldErrors {
  const errors: CheckoutFieldErrors = {};
  if (!values.contactName.trim()) errors.contactName = messages.contactName;
  if (!values.phone.trim()) errors.phone = messages.phone;
  if (!values.deliveryMethod) errors.deliveryMethod = messages.deliveryMethod;
  if (!values.city.trim()) errors.city = messages.city;
  if (!values.height.trim()) errors.height = 'Укажите рост.';
  else if (!/^\d+$/.test(values.height.trim()) || Number(values.height) <= 0 || Number(values.height) > 300) errors.height = messages.height;
  if (!values.weight.trim()) errors.weight = 'Укажите вес.';
  else if (!/^\d+(?:[.,]\d+)?$/.test(values.weight.trim()) || Number(values.weight.replace(',', '.')) <= 0 || Number(values.weight.replace(',', '.')) > 1000) errors.weight = messages.weight;
  return errors;
}

export function mapCheckoutApiValidationErrors(error: unknown): CheckoutFieldErrors | null {
  if (!(error instanceof ApiClientError) || error.status !== 422) return null;
  const detail = (error.details as { detail?: unknown } | null)?.detail;
  if (!Array.isArray(detail)) return {};
  const result: CheckoutFieldErrors = {};
  for (const item of detail) {
    const loc = (item as { loc?: unknown })?.loc;
    if (!Array.isArray(loc)) continue;
    const field = backendFields[String(loc[loc.length - 1])];
    if (field) result[field] = messages[field];
  }
  return result;
}

export const checkoutFieldOrder: CheckoutField[] = ['contactName', 'phone', 'deliveryMethod', 'city', 'height', 'weight'];
