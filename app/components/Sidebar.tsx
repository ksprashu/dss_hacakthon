
import React from 'react';
import { Product } from '../types';

interface SidebarProps {
  products: Product[];
  selectedId: string;
  onSelect: (product: Product) => void;
  onAdd: () => void;
  isAnalyzing: boolean;
}

const Sidebar: React.FC<SidebarProps> = ({ products, selectedId, onSelect, onAdd, isAnalyzing }) => {
  return (
    <div className="w-80 h-full flex flex-col border-r border-stone-200 bg-white shadow-sm z-10">
      <div className="p-6 border-b border-stone-100">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-xl font-bold tracking-tight text-stone-800 uppercase text-xs">Collection</h1>
          <button 
            onClick={onAdd}
            disabled={isAnalyzing}
            className="w-8 h-8 flex items-center justify-center rounded-full bg-stone-900 text-white hover:bg-stone-800 transition-colors disabled:opacity-50"
          >
            {isAnalyzing ? (
               <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            ) : (
              <span className="text-xl leading-none">+</span>
            )}
          </button>
        </div>
        <p className="text-stone-500 text-xs font-medium uppercase tracking-widest">
          {products.length} Items Indexed
        </p>
      </div>

      <div className="flex-1 overflow-y-auto no-scrollbar space-y-4 p-4">
        {products.map((product) => (
          <div
            key={product.id}
            onClick={() => onSelect(product)}
            className={`
              group cursor-pointer rounded-xl transition-all duration-300 overflow-hidden
              ${selectedId === product.id 
                ? 'ring-2 ring-stone-900 shadow-md transform scale-[1.02]' 
                : 'hover:bg-stone-50 ring-1 ring-stone-100 shadow-sm'}
            `}
          >
            <div className="relative aspect-square w-full">
              <img 
                src={product.image} 
                alt={product.label} 
                className="w-full h-full object-cover grayscale-[0.3] group-hover:grayscale-0 transition-all duration-500"
              />
              <div className="absolute inset-0 bg-stone-900/10 group-hover:bg-transparent transition-colors" />
              <div className="absolute bottom-3 left-3 right-3 bg-white/90 backdrop-blur p-3 rounded-lg shadow-sm">
                <h3 className="text-sm font-bold text-stone-900 truncate uppercase">
                  {product.label.split('-').join(' ')}
                </h3>
                <p className="text-[10px] text-stone-500 font-semibold truncate mt-0.5">
                  {product.material_analysis.material_type}
                </p>
                <p className="text-[10px] text-stone-400 mt-1 uppercase tracking-tighter italic">
                  ID: {product.scan_id.split('-').pop()}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Sidebar;
