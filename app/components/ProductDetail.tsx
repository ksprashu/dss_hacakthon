
import React from 'react';
import { Product } from '../types';

interface ProductDetailProps {
  product: Product;
}

const ProgressBar: React.FC<{ label: string; value: number }> = ({ label, value }) => (
  <div className="space-y-1.5">
    <div className="flex justify-between text-[11px] font-bold uppercase tracking-wider text-stone-600">
      <span>{label}</span>
      <span>{value}/10</span>
    </div>
    <div className="h-1.5 w-full bg-stone-100 rounded-full overflow-hidden">
      <div 
        className="h-full bg-stone-800 transition-all duration-1000 ease-out"
        style={{ width: `${value * 10}%` }}
      />
    </div>
  </div>
);

const DetailSection: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="space-y-4">
    <h2 className="text-xs font-bold text-stone-400 uppercase tracking-widest border-b border-stone-100 pb-2">
      {title}
    </h2>
    {children}
  </div>
);

const ProductDetail: React.FC<ProductDetailProps> = ({ product }) => {
  const analysis = product.material_analysis;

  return (
    <div className="flex-1 h-full overflow-y-auto bg-stone-50 flex flex-col no-scrollbar">
      {/* Hero Header */}
      <div className="relative h-96 shrink-0">
        <img 
          src={product.image} 
          alt={product.label} 
          className="w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-stone-900/60 to-transparent" />
        <div className="absolute bottom-12 left-12 max-w-2xl">
          <span className="inline-block px-3 py-1 bg-white/20 backdrop-blur text-white text-[10px] font-bold uppercase tracking-widest rounded mb-4">
            AI Material Identification
          </span>
          <h1 className="text-6xl font-serif text-white italic tracking-tight mb-2">
            {product.label.split('-').join(' ')}
          </h1>
          <p className="text-xl text-stone-200 font-light">
            Composed of premium <span className="font-medium text-white underline decoration-stone-400 underline-offset-4">{analysis.material_type}</span>
          </p>
        </div>
      </div>

      {/* Content Grid */}
      <div className="grid grid-cols-12 gap-12 p-12 max-w-7xl">
        
        {/* Left Column: Texture & Wearable */}
        <div className="col-span-12 lg:col-span-7 space-y-12">
          
          <DetailSection title="Tactile Texture Profile">
            <div className="grid grid-cols-2 gap-8">
              <div className="space-y-6">
                <ProgressBar label="Smoothness" value={Number(analysis.texture_properties.smoothness.value)} />
                <ProgressBar label="Roughness" value={Number(analysis.texture_properties.roughness.value)} />
              </div>
              <div className="space-y-6">
                <ProgressBar label="Stretch" value={Number(analysis.texture_properties.stretchiness.value)} />
                <div className="space-y-1.5">
                  <div className="text-[11px] font-bold uppercase tracking-wider text-stone-600">Density/Thickness</div>
                  <div className="text-sm font-medium text-stone-900 bg-stone-100 py-1.5 px-3 rounded inline-block">
                    {analysis.texture_properties.thickness.value}
                  </div>
                </div>
              </div>
            </div>
            <p className="text-sm text-stone-500 leading-relaxed italic mt-4 bg-white p-4 rounded-lg shadow-sm border border-stone-100">
              "{analysis.texture_properties.smoothness.description}"
            </p>
          </DetailSection>

          <DetailSection title="Performance & Comfort">
            <div className="grid grid-cols-2 gap-8">
              <ProgressBar label="Breathability" value={Number(analysis.wearable_properties.breathability.value)} />
              <ProgressBar label="Moisture Wicking" value={Number(analysis.wearable_properties.moisture_wicking.value)} />
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              {analysis.wearable_properties.skin_contact.recommended && (
                <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 text-green-700 rounded-full text-xs font-bold border border-green-100">
                   <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/></svg>
                   Hypoallergenic / Skin Safe
                </div>
              )}
              <div className="px-3 py-1.5 bg-stone-900 text-white rounded-full text-xs font-bold">
                 Insulation: {analysis.wearable_properties.insulation.value}/10
              </div>
            </div>
          </DetailSection>

          <DetailSection title="Key Characteristics">
            <ul className="space-y-3">
              {analysis.key_characteristics.map((item, i) => (
                <li key={i} className="flex items-start gap-4 text-stone-700 text-sm leading-relaxed">
                  <span className="mt-2 w-1.5 h-1.5 bg-stone-300 rounded-full shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </DetailSection>

        </div>

        {/* Right Column: Weather, Usage, Color */}
        <div className="col-span-12 lg:col-span-5 space-y-12">
          
          <DetailSection title="Environmental Suitability">
            <div className="space-y-4">
              {[
                { label: 'Warm Weather', data: analysis.weather_recommendations.warm_weather, icon: '☀️' },
                { label: 'Cool Weather', data: analysis.weather_recommendations.cool_weather, icon: '❄️' },
                { label: 'Indoor / Office', data: analysis.weather_recommendations.indoor, icon: '🏠' },
              ].map((item, i) => (
                <div key={i} className={`p-4 rounded-xl border transition-all ${item.data.suitable ? 'bg-white border-stone-200' : 'bg-stone-50 border-stone-100 opacity-60'}`}>
                   <div className="flex items-center justify-between mb-2">
                     <span className="text-lg">{item.icon}</span>
                     <span className="text-[10px] font-bold uppercase tracking-widest text-stone-500">{item.label}</span>
                   </div>
                   <p className="text-xs text-stone-600 leading-tight">
                     {item.data.description}
                   </p>
                </div>
              ))}
            </div>
          </DetailSection>

          <DetailSection title="Optimal Application">
            <div className="flex flex-wrap gap-2">
              {analysis.ideal_usage_scenarios.map((scenario, i) => (
                <span key={i} className="px-3 py-1.5 bg-white border border-stone-200 text-stone-600 rounded text-xs font-medium">
                  {scenario}
                </span>
              ))}
            </div>
          </DetailSection>

          <DetailSection title="Chromatic Analysis">
            <div className="bg-stone-900 rounded-2xl p-6 text-white overflow-hidden relative">
              <div className="relative z-10">
                <div className="flex justify-between items-center mb-4">
                   <h3 className="text-xs font-bold uppercase tracking-[0.2em] text-stone-400">Measured Palette</h3>
                   <div className="w-4 h-4 rounded-full border border-stone-700" style={{ backgroundColor: analysis.color_analysis.true_color.toLowerCase().includes('teal') ? '#008080' : '#000080' }} />
                </div>
                <p className="text-lg font-serif italic mb-2">{analysis.color_analysis.true_color}</p>
                <p className="text-xs text-stone-400 font-light leading-relaxed">
                  {analysis.color_analysis.color_consistency}
                </p>
              </div>
              <div className="absolute top-0 right-0 w-24 h-24 bg-white/5 rounded-full -mr-12 -mt-12" />
            </div>
          </DetailSection>

        </div>
      </div>

      {/* Footer Meta */}
      <div className="mt-auto border-t border-stone-100 bg-white p-6 flex justify-between items-center text-[10px] font-bold text-stone-400 uppercase tracking-widest">
         <span>Scan ID: {product.scan_id}</span>
         <span>Confidence: {analysis.confidence}</span>
         <span className="text-stone-300">© 2026 MaterialLab AI</span>
      </div>
    </div>
  );
};

export default ProductDetail;
