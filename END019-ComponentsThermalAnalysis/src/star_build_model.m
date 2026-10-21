function M = star_build_model(cfg)
% STAR_BUILD_MODEL  Costruisce nodi, capacita', ottiche e rete conduttiva.
%   Nodi: 6 facce (di cui 4 pannelli solari laterali) + eventuali pannelli
%   dispiegabili + nodi interni scelti (1: CTR | 2: CTR,BAT | 3: CTR,BAT,SAR).
%   Ottiche dei pannelli solari = dalla calibrazione (cfg.sat).

nf = 6;
npan = 0; if cfg.dep.enable, npan = cfg.dep.nwings; end
nInt = numel(cfg.nodes.names);
Nn = nf + npan + nInt;

names = {'+X','-X','+Y','-Y','+Z','-Z'};
for w=1:npan, names{end+1}=sprintf('PANdep%d',w); end %#ok<AGROW>
names = [names, cfg.nodes.names];

normals = [1 0 0;-1 0 0;0 1 0;0 -1 0;0 0 1;0 0 -1]';
Aface = cfg.sat.Aface(:);

% capacita' C = m*cp
Cface = cfg.sat.rhoA*Aface*cfg.sat.faceCp;
Cpan  = zeros(npan,1); epsApan = zeros(npan,1);
for w=1:npan
    Cpan(w)    = cfg.dep.mass*cfg.dep.cp;
    epsApan(w) = (cfg.dep.epsF+cfg.dep.epsB)*cfg.dep.A;   % irraggia da entrambe le facce
end
Cint = cfg.nodes.mass(:).*cfg.nodes.cp(:);
C = [Cface; Cpan; Cint];

epsA = [cfg.sat.eps(:).*Aface; epsApan; zeros(nInt,1)];

% indici nodi interni (BAT/SAR possono non esistere -> [])
gi   = @(nm) find(strcmp(names,nm),1);
iCTR = gi('CTR');
iBAT = gi('BAT');
iSAR = gi(cfg.sar.node);

% rete conduttiva (link condizionali ai nodi presenti)
links = zeros(0,3);
for fi=1:6, links(end+1,:)=[iCTR fi cfg.cond.Gw_ctr/6]; end %#ok<AGROW> centrale <-> facce
if ~isempty(iBAT)
    for fi=1:6, links(end+1,:)=[iBAT fi cfg.cond.Gw_bat/6]; end %#ok<AGROW>
    links(end+1,:)=[iBAT iCTR cfg.cond.Gc_bc];                  %#ok<AGROW>
end
if ~isempty(iSAR)
    links(end+1,:)=[iSAR iCTR cfg.cond.G_sarbus];                        %#ok<AGROW>
    links(end+1,:)=[iSAR cfg.cond.radFace cfg.cond.G_sarrad];            %#ok<AGROW>
end
for w=1:npan, links(end+1,:)=[nf+w iCTR cfg.dep.Ghinge]; end %#ok<AGROW> cerniera pannello-bus
Lc = zeros(Nn);
for k=1:size(links,1)
    i=links(k,1); j=links(k,2); g=links(k,3);
    Lc(i,i)=Lc(i,i)+g; Lc(j,j)=Lc(j,j)+g; Lc(i,j)=Lc(i,j)-g; Lc(j,i)=Lc(j,i)-g;
end

% potenze interne costanti (SAR a parte)
Pc = zeros(Nn,1);
for m=1:nInt, Pc(nf+npan+m)=cfg.nodes.Pconst(m); end

% classificazione dei nodi per l'output
isExt   = [true(1,nf+npan) false(1,nInt)];
isSolar = false(1,Nn);
isSolar(cfg.sat.solar_faces) = true;   % pannelli solari body-mounted (facce laterali)
for w=1:npan, isSolar(nf+w)=true; end  % pannelli solari dispiegabili

M.nf=nf; M.npan=npan; M.nInt=nInt; M.Nn=Nn; M.names=names;
M.normals=normals; M.Aface=Aface; M.C=C; M.epsA=epsA; M.Lc=Lc; M.Pc=Pc;
M.iCTR=iCTR; M.iBAT=iBAT; M.iSAR=iSAR;
M.isExt=isExt; M.isSolar=isSolar;
M.alpha=cfg.sat.alpha; M.eps=cfg.sat.eps;
end
