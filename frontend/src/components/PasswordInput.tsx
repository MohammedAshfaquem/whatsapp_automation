import React, {useState} from 'react';
import {Eye,EyeOff} from 'lucide-react';
type Props=Omit<React.InputHTMLAttributes<HTMLInputElement>,'type'> & {visibilityLabel?:string};
export const PasswordInput:React.FC<Props>=({visibilityLabel='password',style,...props})=>{
 const [visible,setVisible]=useState(false);
 return <span style={{position:'relative',display:'block',width:'100%'}}><input {...props} type={visible?'text':'password'} style={{...style,paddingRight:'3rem'}}/><button type="button" disabled={props.disabled} aria-label={`${visible?'Hide':'Show'} ${visibilityLabel}`} aria-pressed={visible} onClick={()=>setVisible(v=>!v)} onMouseDown={e=>e.preventDefault()} style={{position:'absolute',right:8,top:'50%',transform:'translateY(-50%)',border:0,background:'transparent',color:"var(--text-muted)",padding:6,cursor:'pointer',display:'flex'}}>{visible?<EyeOff size={19} aria-hidden="true"/>:<Eye size={19} aria-hidden="true"/>}</button></span>;
};
