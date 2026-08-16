# Company Onboarding - Frontend Integration Guide

## Quick Start

### Base URL
```
http://localhost:8000/api  (development)
https://your-domain.com/api  (production)
```

### Authentication
All requests require JWT token in header:
```javascript
headers: {
  'Authorization': `Bearer ${accessToken}`
}
```

---

## API Endpoints

### 1. Check Onboarding Status

**When to call**: After login/signup, on app initialization

```javascript
// Check if onboarding is needed
const response = await fetch('/api/companies/onboarding/status', {
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});

const data = await response.json();

if (data.data.onboarding_completed) {
  // Go to dashboard
  navigate('/dashboard');
} else {
  // Show onboarding wizard
  navigate('/onboarding');
}
```

**Response Example**:
```json
{
  "success": true,
  "data": {
    "onboarding_completed": false,
    "company": {
      "id": 1,
      "name": "شركة الأمل",
      "logo": null,
      "cover": null,
      "governorate": null,
      "region": null,
      "description": null,
      "business_type": null
    }
  }
}
```

---

### 2. Get Locations (Governorates & Regions)

**When to call**: When showing Step 2 (location selection)

```javascript
const response = await fetch('/api/companies/locations', {
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});

const { data } = await response.json();
const locations = data.locations;

// locations is an array of { governorate, regions[] }
```

**Response Structure**:
```json
{
  "success": true,
  "data": {
    "locations": [
      {
        "governorate": "دمشق",
        "regions": ["المزة", "المالكي", "أبو رمانة", ...]
      },
      {
        "governorate": "حلب",
        "regions": ["حلب المدينة", "منبج", ...]
      }
    ]
  }
}
```

**UI Implementation**:
```jsx
// Example React component
function LocationStep({ onNext }) {
  const [locations, setLocations] = useState([]);
  const [selectedGov, setSelectedGov] = useState('');
  const [selectedRegion, setSelectedRegion] = useState('');

  useEffect(() => {
    fetch('/api/companies/locations', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => r.json())
      .then(data => setLocations(data.data.locations));
  }, []);

  const regions = locations.find(
    loc => loc.governorate === selectedGov
  )?.regions || [];

  return (
    <div>
      <h2>أين تقع شركتك؟</h2>
      
      <select onChange={e => setSelectedGov(e.target.value)}>
        <option>إختر المحافظة</option>
        {locations.map(loc => (
          <option key={loc.governorate}>{loc.governorate}</option>
        ))}
      </select>

      <select onChange={e => setSelectedRegion(e.target.value)}>
        <option>إختر المنطقة</option>
        {regions.map(region => (
          <option key={region}>{region}</option>
        ))}
      </select>

      <button onClick={() => onNext({ governorate: selectedGov, region: selectedRegion })}>
        التالي
      </button>
    </div>
  );
}
```

---

### 3. Get Business Types

**When to call**: When showing Step 4 (business type selection)

```javascript
const response = await fetch('/api/companies/business-types', {
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});

const { data } = await response.json();
const businessTypes = data.business_types;
```

**Response Structure**:
```json
{
  "success": true,
  "data": {
    "business_types": [
      { "value": "food_products", "label": "مواد غذائية" },
      { "value": "electronics", "label": "إلكترونيات" },
      { "value": "cosmetics", "label": "مستحضرات تجميل" },
      { "value": "medical_supplies", "label": "أدوية ومستلزمات طبية" },
      { "value": "home_tools", "label": "أدوات منزلية" },
      { "value": "clothing", "label": "ألبسة" }
    ]
  }
}
```

**UI Implementation**:
```jsx
function BusinessTypeStep({ onComplete }) {
  const [types, setTypes] = useState([]);
  const [selected, setSelected] = useState('');

  useEffect(() => {
    fetch('/api/companies/business-types', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => r.json())
      .then(data => setTypes(data.data.business_types));
  }, []);

  return (
    <div>
      <h2>ما هو نشاط شركتك؟</h2>
      <div className="business-types-grid">
        {types.map(type => (
          <button
            key={type.value}
            className={selected === type.value ? 'selected' : ''}
            onClick={() => setSelected(type.value)}
          >
            {type.label}
          </button>
        ))}
      </div>
      <button onClick={() => onComplete({ business_type: selected })}>
        إنهاء الإعداد
      </button>
    </div>
  );
}
```

---

### 4. Submit Onboarding Data

**When to call**: On final step or when user clicks "skip"

```javascript
// Prepare form data
const formData = new FormData();

// Only append fields that have values
if (logo) formData.append('logo', logo);
if (cover) formData.append('cover', cover);
if (governorate) formData.append('governorate', governorate);
if (region) formData.append('region', region);
if (description) formData.append('description', description);
if (businessType) formData.append('business_type', businessType);

// Submit
const response = await fetch('/api/companies/onboarding', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
    // DON'T set Content-Type - browser will set it with boundary
  },
  body: formData
});

const result = await response.json();

if (result.success) {
  // Onboarding completed!
  navigate('/dashboard');
} else {
  // Show validation errors
  console.error(result.errors);
}
```

**Important Notes**:
- Use `FormData` for file uploads
- DON'T set `Content-Type` header (browser sets it automatically with boundary)
- All fields are optional
- Empty submission is valid (marks onboarding as complete)

---

## Complete React Example

```jsx
import { useState } from 'react';

function OnboardingWizard({ accessToken, onComplete }) {
  const [step, setStep] = useState(1);
  const [data, setData] = useState({
    logo: null,
    cover: null,
    governorate: '',
    region: '',
    description: '',
    business_type: ''
  });

  // Update state from any step
  const updateData = (updates) => {
    setData(prev => ({ ...prev, ...updates }));
  };

  // Submit all data at once
  const handleComplete = async () => {
    const formData = new FormData();
    
    if (data.logo) formData.append('logo', data.logo);
    if (data.cover) formData.append('cover', data.cover);
    if (data.governorate) formData.append('governorate', data.governorate);
    if (data.region) formData.append('region', data.region);
    if (data.description) formData.append('description', data.description);
    if (data.business_type) formData.append('business_type', data.business_type);

    try {
      const response = await fetch('/api/companies/onboarding', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${accessToken}` },
        body: formData
      });

      const result = await response.json();

      if (result.success) {
        onComplete(result.data.company);
      } else {
        alert('حدث خطأ: ' + JSON.stringify(result.errors));
      }
    } catch (error) {
      alert('حدث خطأ في الاتصال');
    }
  };

  // Skip onboarding
  const handleSkip = async () => {
    // Submit empty form to mark as completed
    try {
      const response = await fetch('/api/companies/onboarding', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${accessToken}` },
        body: new FormData() // Empty form
      });

      const result = await response.json();
      if (result.success) {
        onComplete(result.data.company);
      }
    } catch (error) {
      alert('حدث خطأ في الاتصال');
    }
  };

  return (
    <div className="onboarding-wizard">
      {/* Progress indicator */}
      <div className="progress">
        <span className={step >= 1 ? 'active' : ''}>1</span>
        <span className={step >= 2 ? 'active' : ''}>2</span>
        <span className={step >= 3 ? 'active' : ''}>3</span>
        <span className={step >= 4 ? 'active' : ''}>4</span>
      </div>

      {/* Step content */}
      {step === 1 && (
        <Step1_LogoCover 
          data={data} 
          updateData={updateData} 
          onNext={() => setStep(2)} 
        />
      )}
      {step === 2 && (
        <Step2_Location 
          data={data} 
          updateData={updateData} 
          onNext={() => setStep(3)} 
          onBack={() => setStep(1)} 
          token={accessToken}
        />
      )}
      {step === 3 && (
        <Step3_Description 
          data={data} 
          updateData={updateData} 
          onNext={() => setStep(4)} 
          onBack={() => setStep(2)} 
        />
      )}
      {step === 4 && (
        <Step4_BusinessType 
          data={data} 
          updateData={updateData} 
          onComplete={handleComplete} 
          onBack={() => setStep(3)} 
          token={accessToken}
        />
      )}

      {/* Skip button (shown on all steps) */}
      <button className="skip-btn" onClick={handleSkip}>
        تخطي الإعداد
      </button>
    </div>
  );
}
```

---

## File Upload Example

```jsx
function Step1_LogoCover({ data, updateData, onNext }) {
  const [logoPreview, setLogoPreview] = useState(null);
  const [coverPreview, setCoverPreview] = useState(null);

  const handleLogoChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      // Validate file size
      if (file.size > 2 * 1024 * 1024) {
        alert('حجم الشعار يجب أن يكون أقل من 2 ميغابايت');
        return;
      }
      
      updateData({ logo: file });
      setLogoPreview(URL.createObjectURL(file));
    }
  };

  const handleCoverChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      // Validate file size
      if (file.size > 5 * 1024 * 1024) {
        alert('حجم الغلاف يجب أن يكون أقل من 5 ميغابايت');
        return;
      }
      
      updateData({ cover: file });
      setCoverPreview(URL.createObjectURL(file));
    }
  };

  return (
    <div>
      <h2>الشعار والغلاف</h2>

      {/* Logo upload */}
      <div className="upload-box">
        <input 
          type="file" 
          accept="image/png,image/jpeg,image/jpg,image/svg+xml"
          onChange={handleLogoChange}
          id="logo-upload"
          style={{ display: 'none' }}
        />
        <label htmlFor="logo-upload">
          {logoPreview ? (
            <img src={logoPreview} alt="Logo preview" />
          ) : (
            <div>اضغط لرفع شعار الشركة</div>
          )}
        </label>
      </div>

      {/* Cover upload */}
      <div className="upload-box">
        <input 
          type="file" 
          accept="image/png,image/jpeg,image/jpg"
          onChange={handleCoverChange}
          id="cover-upload"
          style={{ display: 'none' }}
        />
        <label htmlFor="cover-upload">
          {coverPreview ? (
            <img src={coverPreview} alt="Cover preview" />
          ) : (
            <div>اضغط لرفع صورة غلاف الشركة</div>
          )}
        </label>
      </div>

      <button onClick={onNext}>التالي</button>
    </div>
  );
}
```

---

## Error Handling

```javascript
async function submitOnboarding(formData, accessToken) {
  try {
    const response = await fetch('/api/companies/onboarding', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${accessToken}` },
      body: formData
    });

    const result = await response.json();

    if (!response.ok) {
      // Handle validation errors
      if (response.status === 400) {
        // Show field-specific errors
        Object.entries(result.errors).forEach(([field, messages]) => {
          messages.forEach(msg => {
            showError(`${field}: ${msg}`);
          });
        });
      } else if (response.status === 403) {
        // Not authorized
        showError('يجب تسجيل الدخول أولاً');
      } else {
        // Other errors
        showError(result.message || 'حدث خطأ غير متوقع');
      }
      return null;
    }

    return result.data.company;
  } catch (error) {
    showError('حدث خطأ في الاتصال بالخادم');
    return null;
  }
}
```

---

## Validation Rules

### Logo
- **Formats**: PNG, JPG, JPEG, SVG
- **Max Size**: 2MB
- **Recommended**: 512x512px (square)

### Cover
- **Formats**: PNG, JPG, JPEG
- **Max Size**: 5MB
- **Recommended**: 16:9 or 21:9 aspect ratio

### Description
- **Max Length**: 500 characters
- **Type**: Text

### Governorate & Region
- Must select from provided lists
- Region must match selected governorate

### Business Type
- Must select from provided options
- Values: `food_products`, `electronics`, `cosmetics`, `medical_supplies`, `home_tools`, `clothing`

---

## Common Issues

### Issue: CORS Error
**Solution**: Backend should have proper CORS configuration
```python
# Backend settings should include:
CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]
```

### Issue: File Not Uploading
**Solution**: 
- Don't set Content-Type header (let browser set it)
- Use FormData correctly
- Check file size limits

### Issue: Token Expired
**Solution**: Implement token refresh logic
```javascript
if (response.status === 401) {
  // Refresh token and retry
  await refreshAccessToken();
  return retryRequest();
}
```

---

## Testing Checklist

- [ ] Can view onboarding status after signup
- [ ] Can skip onboarding with empty submission
- [ ] Can upload logo and cover images
- [ ] Can select governorate and region
- [ ] Can enter description
- [ ] Can select business type
- [ ] Can complete onboarding with all fields
- [ ] Can complete onboarding with partial fields
- [ ] Validation errors display correctly
- [ ] File size limits enforced
- [ ] Unauthorized access blocked
- [ ] Can edit company profile later (same endpoint)

---

## Support

For questions or issues:
- API Documentation: `docs/api_auth_endpoints.md`
- Implementation Details: `docs/onboarding_implementation_summary.md`
- Backend Team: Contact backend developers

**Version**: 1.0  
**Last Updated**: August 16, 2026
