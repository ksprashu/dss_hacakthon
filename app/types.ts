
export interface TextureProperty {
  value: number | string;
  description: string;
}

export interface WearableProperty {
  value?: number;
  recommended?: boolean;
  description: string;
}

export interface WeatherRecommendation {
  suitable: boolean;
  description: string;
}

export interface MaterialAnalysis {
  material_type: string;
  confidence: string;
  texture_properties: {
    smoothness: TextureProperty;
    roughness: TextureProperty;
    stretchiness: TextureProperty;
    thickness: TextureProperty;
  };
  wearable_properties: {
    skin_contact: WearableProperty;
    breathability: WearableProperty;
    moisture_wicking: WearableProperty;
    insulation: WearableProperty;
  };
  weather_recommendations: {
    cool_weather: WeatherRecommendation;
    warm_weather: WeatherRecommendation;
    indoor: WeatherRecommendation;
  };
  key_characteristics: string[];
  ideal_usage_scenarios: string[];
  color_analysis: {
    true_color: string;
    color_consistency: string;
  };
}

export interface Product {
  id: string;
  scan_id: string;
  label: string;
  image: string;
  material_analysis: MaterialAnalysis;
}
