import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { it, expect, vi } from 'vitest';
import Modal from '../src/components/Modal';
it('closes on X, Escape and backdrop without submitting', () => {
 const close=vi.fn(), submit=vi.fn(); const {container}=render(<form onSubmit={submit}><Modal title="Example" onClose={close}><input /></Modal></form>);
 fireEvent.click(screen.getByRole('button',{name:'Close Example'})); fireEvent.keyDown(document,{key:'Escape'}); fireEvent.click(container.querySelector('.modal-backdrop')!); fireEvent.click(screen.getByRole('dialog'));
 expect(close).toHaveBeenCalledTimes(3); expect(submit).not.toHaveBeenCalled();
});
it('closes only the topmost dialog, traps and restores focus and scroll', () => {
 function Example(){const [parent,p]=useState(false),[child,c]=useState(false);return <><button onClick={()=>p(true)}>Open</button>{parent&&<Modal title="Parent" onClose={()=>p(false)}><button onClick={()=>c(true)}>Child</button>{child&&<Modal title="Child" onClose={()=>c(false)}><button>Last</button></Modal>}</Modal>}</>;}
 render(<Example/>);const opener=screen.getByText('Open');opener.focus();fireEvent.click(opener);const childOpener=screen.getByText('Child');childOpener.focus();fireEvent.click(childOpener);
 fireEvent.click(screen.getByRole('dialog',{name:'Parent'}).parentElement!); expect(screen.getByRole('dialog',{name:'Child'})).toBeTruthy(); fireEvent.click(screen.getByRole('button',{name:'Close Parent'})); expect(screen.getByRole('dialog',{name:'Parent'})).toBeTruthy();
 const close=screen.getByRole('button',{name:'Close Child'});expect(document.activeElement).toBe(close);fireEvent.keyDown(document,{key:'Tab',shiftKey:true});expect(document.activeElement).toBe(screen.getByText('Last'));fireEvent.keyDown(document,{key:'Tab'});expect(document.activeElement).toBe(close);
 fireEvent.keyDown(document,{key:'Escape'});expect(screen.queryByRole('dialog',{name:'Child'})).toBeNull();expect(screen.getByRole('dialog',{name:'Parent'})).toBeTruthy();expect(document.activeElement).toBe(childOpener);expect(document.body.style.overflow).toBe('hidden');fireEvent.keyDown(document,{key:'Escape'});expect(document.activeElement).toBe(opener);expect(document.body.style.overflow).toBe('');
});

