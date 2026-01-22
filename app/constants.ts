
import { Product } from './types';

export const INITIAL_PRODUCTS: Product[] = [
  {
    id: "1",
    scan_id: "20260122-192049-631f0791",
    label: "branded-mens-polo-tshirt",
    image: "https://images.unsplash.com/photo-1626497748470-284d81f9f214?q=80&w=1000&auto=format&fit=crop", // Simulated placeholder from the provided image description
    material_analysis: {
      material_type: "Cotton Piqué Blend",
      confidence: "high",
      texture_properties: {
        smoothness: { value: 6, description: "Generally soft surface typical of cotton knits with a slightly raised grain." },
        roughness: { value: 3, description: "The piqué weave creates a subtle pebbled texture rather than true roughness." },
        stretchiness: { value: 5, description: "Moderate natural elasticity provided by the knit structure." },
        thickness: { value: "medium", description: "Standard polo fabric weight, offering good structural integrity." }
      },
      wearable_properties: {
        skin_contact: { recommended: true, description: "Soft natural fibers and breathable weave make it comfortable against the skin." },
        breathability: { value: 8, description: "The open piqué knit allows for excellent air circulation." },
        moisture_wicking: { value: 6, description: "Good absorption of sweat, though cotton blends dry slower than pure synthetics." },
        insulation: { value: 3, description: "Low thermal retention, designed primarily for cooling." }
      },
      weather_recommendations: {
        cool_weather: { suitable: true, description: "Suitable as a base layer under a jacket or sweater." },
        warm_weather: { suitable: true, description: "Highly suitable due to breathability and light weight." },
        indoor: { suitable: true, description: "Ideal for office or casual indoor environments." }
      },
      key_characteristics: ["Classic piqué knit texture", "Breathable and durable construction", "Casual yet professional appearance"],
      ideal_usage_scenarios: ["Business casual office wear", "Outdoor corporate events", "Active lifestyle or golf"],
      color_analysis: {
        true_color: "Teal/Aquamarine",
        color_consistency: "The color shifts from a warmer cyan under indoor lights to a more saturated, cool blue-green in natural light."
      }
    }
  },
  {
    id: "2",
    scan_id: "20260122-200309-f9046b28",
    label: "cotton-mens-sock",
    image: "https://images.unsplash.com/photo-1586350977771-b3b0abd50c82?q=80&w=1000&auto=format&fit=crop",
    material_analysis: {
      material_type: "Cotton Ribbed",
      confidence: "high",
      texture_properties: {
        smoothness: { value: 7, description: "Soft knit surface providing a comfortable tactile feel." },
        roughness: { value: 3, description: "Low surface friction with minor texture produced by the vertical ribbing." },
        stretchiness: { value: 8, description: "Highly elastic knit structure that expands easily and retains shape." },
        thickness: { value: "medium", description: "Standard weight typical of everyday men's casual or dress socks." }
      },
      wearable_properties: {
        skin_contact: { recommended: true, description: "Designed for direct skin contact; non-irritating and soft." },
        breathability: { value: 8, description: "Natural cotton fibers provide excellent air circulation." },
        moisture_wicking: { value: 5, description: "Good absorption properties, though it dries slower than specialized synthetics." },
        insulation: { value: 4, description: "Provides light warmth suitable for standard indoor and mild outdoor temperatures." }
      },
      weather_recommendations: {
        cool_weather: { suitable: true, description: "Offers basic protection and comfort in mild cool weather." },
        warm_weather: { suitable: true, description: "Breathable material helps keep feet comfortable in warm conditions." },
        indoor: { suitable: true, description: "Perfect for all-day indoor use in home or office environments." }
      },
      key_characteristics: ["Classic vertical ribbed knit pattern", "Soft and flexible cotton-based fabric", "Excellent stretch and recovery"],
      ideal_usage_scenarios: ["Everyday casual footwear", "Professional business attire", "Lightweight comfort for indoor wear"],
      color_analysis: {
        true_color: "Navy Blue",
        color_consistency: "High consistency; maintains a deep blue appearance across varied lighting conditions."
      }
    }
  }
];
