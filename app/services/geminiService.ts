
import { GoogleGenAI, Type } from "@google/genai";
import { MaterialAnalysis } from "../types";

const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

const MATERIAL_ANALYSIS_SCHEMA = {
  type: Type.OBJECT,
  properties: {
    material_type: { type: Type.STRING },
    confidence: { type: Type.STRING },
    texture_properties: {
      type: Type.OBJECT,
      properties: {
        smoothness: {
          type: Type.OBJECT,
          properties: {
            value: { type: Type.NUMBER },
            description: { type: Type.STRING }
          }
        },
        roughness: {
          type: Type.OBJECT,
          properties: {
            value: { type: Type.NUMBER },
            description: { type: Type.STRING }
          }
        },
        stretchiness: {
          type: Type.OBJECT,
          properties: {
            value: { type: Type.NUMBER },
            description: { type: Type.STRING }
          }
        },
        thickness: {
          type: Type.OBJECT,
          properties: {
            value: { type: Type.STRING },
            description: { type: Type.STRING }
          }
        }
      }
    },
    wearable_properties: {
      type: Type.OBJECT,
      properties: {
        skin_contact: {
          type: Type.OBJECT,
          properties: {
            recommended: { type: Type.BOOLEAN },
            description: { type: Type.STRING }
          }
        },
        breathability: {
          type: Type.OBJECT,
          properties: {
            value: { type: Type.NUMBER },
            description: { type: Type.STRING }
          }
        },
        moisture_wicking: {
          type: Type.OBJECT,
          properties: {
            value: { type: Type.NUMBER },
            description: { type: Type.STRING }
          }
        },
        insulation: {
          type: Type.OBJECT,
          properties: {
            value: { type: Type.NUMBER },
            description: { type: Type.STRING }
          }
        }
      }
    },
    weather_recommendations: {
      type: Type.OBJECT,
      properties: {
        cool_weather: {
          type: Type.OBJECT,
          properties: {
            suitable: { type: Type.BOOLEAN },
            description: { type: Type.STRING }
          }
        },
        warm_weather: {
          type: Type.OBJECT,
          properties: {
            suitable: { type: Type.BOOLEAN },
            description: { type: Type.STRING }
          }
        },
        indoor: {
          type: Type.OBJECT,
          properties: {
            suitable: { type: Type.BOOLEAN },
            description: { type: Type.STRING }
          }
        }
      }
    },
    key_characteristics: {
      type: Type.ARRAY,
      items: { type: Type.STRING }
    },
    ideal_usage_scenarios: {
      type: Type.ARRAY,
      items: { type: Type.STRING }
    },
    color_analysis: {
      type: Type.OBJECT,
      properties: {
        true_color: { type: Type.STRING },
        color_consistency: { type: Type.STRING }
      }
    }
  }
};

export const analyzeProductImage = async (base64Image: string): Promise<MaterialAnalysis> => {
  const response = await ai.models.generateContent({
    model: 'gemini-3-flash-preview',
    contents: [
      {
        parts: [
          {
            inlineData: {
              mimeType: 'image/jpeg',
              data: base64Image.split(',')[1] || base64Image
            }
          },
          {
            text: "Analyze this product's material properties. Provide a detailed material analysis including texture, wearable properties, weather suitability, key characteristics, ideal usage, and color analysis. Be technical and descriptive."
          }
        ]
      }
    ],
    config: {
      responseMimeType: 'application/json',
      responseSchema: MATERIAL_ANALYSIS_SCHEMA
    }
  });

  return JSON.parse(response.text);
};
