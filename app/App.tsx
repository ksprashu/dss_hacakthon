
import React, { useState, useCallback, useRef } from 'react';
import Sidebar from './components/Sidebar';
import ProductDetail from './components/ProductDetail';
import { Product } from './types';
import { INITIAL_PRODUCTS } from './constants';
import { analyzeProductImage } from './services/geminiService';

const App: React.FC = () => {
  const [products, setProducts] = useState<Product[]>(INITIAL_PRODUCTS);
  const [selectedProduct, setSelectedProduct] = useState<Product>(INITIAL_PRODUCTS[0]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleAddProduct = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsAnalyzing(true);
    try {
      const reader = new FileReader();
      reader.onload = async (event) => {
        const base64 = event.target?.result as string;
        
        try {
          const analysis = await analyzeProductImage(base64);
          const newProduct: Product = {
            id: Date.now().toString(),
            scan_id: `SCAN-${Date.now()}-${Math.random().toString(36).substring(7).toUpperCase()}`,
            label: analysis.material_type.toLowerCase().split(' ').join('-'),
            image: base64,
            material_analysis: analysis
          };
          
          setProducts(prev => [newProduct, ...prev]);
          setSelectedProduct(newProduct);
        } catch (err) {
          console.error("AI Analysis failed:", err);
          alert("Failed to analyze image. Please ensure you have a valid API Key and image.");
        } finally {
          setIsAnalyzing(false);
        }
      };
      reader.readAsDataURL(file);
    } catch (err) {
      console.error("File processing failed:", err);
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-stone-50 font-sans selection:bg-stone-900 selection:text-white">
      {/* Invisible file input */}
      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileChange} 
        className="hidden" 
        accept="image/*"
      />

      {/* Global Status Banner if analyzing */}
      {isAnalyzing && (
        <div className="fixed top-0 left-0 right-0 h-1 bg-stone-900 z-50 overflow-hidden">
          <div className="h-full bg-stone-200 animate-[loading_2s_infinite_linear]" style={{ width: '40%' }}></div>
        </div>
      )}

      {/* Main UI Split */}
      <Sidebar 
        products={products} 
        selectedId={selectedProduct.id} 
        onSelect={setSelectedProduct} 
        onAdd={handleAddProduct}
        isAnalyzing={isAnalyzing}
      />
      
      <main className="flex-1 relative">
        {selectedProduct ? (
          <ProductDetail product={selectedProduct} />
        ) : (
          <div className="h-full flex items-center justify-center text-stone-400 font-serif italic text-2xl">
            Select an item to view material insights
          </div>
        )}
      </main>

      <style>{`
        @keyframes loading {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(250%); }
        }
      `}</style>
    </div>
  );
};

export default App;
